"""Fetch changes in local worktrees."""

from functools import lru_cache
from typing import Dict, List, Tuple

from odev.common import args, progress, string
from odev.common.commands import GitCommand
from odev.common.console import Colors
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class FetchCommand(GitCommand):
    """Fetch changes in local Odoo worktrees managed by odev."""

    _name = "fetch"

    worktree = args.String(
        aliases=["--worktree", "-w"],
        description="Name of a specific worktree to fetch changes for.",
        nargs="?",
    )

    def run(self):
        changes_by_worktree = self.grouped_changes()
        sorted_worktree: List[str] = sorted(
            changes_by_worktree.keys(),
            key=lambda worktree: (
                -int(worktree.partition(".")[0]) if worktree[0].isdigit() else -float("inf"),
                worktree,
            ),
        )

        for worktree in sorted_worktree:
            self.run_hook(worktree, changes_by_worktree[worktree])

    def run_hook(self, worktree: str, changes: List[Tuple[str, int, int]]):
        """Print a summary of the pending changes for a worktree."""
        self.print_table(
            [
                [
                    repository,
                    str(behind) if not behind else string.stylize(str(behind), Colors.RED),
                    str(ahead) if not ahead else string.stylize(str(ahead), Colors.RED),
                ]
                for repository, behind, ahead in changes
            ],
            worktree,
        )

    @lru_cache
    def grouped_changes(self) -> Dict[str, List[Tuple[str, int, int]]]:
        """Group changes by version."""
        changes: Dict[str, List[Tuple[str, int, int]]] = {}

        for name, worktrees in self.grouped_worktrees.items():
            if self.args.worktree and self.args.worktree != name:
                continue

            fetch_message = f"Fetching changes in worktree {name!r}"

            with progress.spinner(fetch_message):
                for worktree in worktrees:
                    if not worktree.detached:
                        with progress.spinner(
                            f"{fetch_message} of repository {worktree.connector.name!r} for version {worktree.branch!r}"
                        ):
                            worktree.repository.remotes.origin.fetch()

                    changes.setdefault(name, []).append((worktree.connector.name, *worktree.pending_changes()))

        if not changes:
            if self.args.worktree:
                raise self.error(f"Worktree with name {self.args.name!r} does not exist")
            raise self.error("No worktrees found")

        return changes
