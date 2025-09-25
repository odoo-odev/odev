"""Fetch changes in local worktrees."""

from functools import lru_cache

from odev.common import args, string
from odev.common.commands import GitCommand
from odev.common.console import TableHeader
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class FetchCommand(GitCommand):
    """Fetch changes in local Odoo worktrees managed by odev."""

    _name = "fetch"

    worktree = args.String(
        aliases=["-w", "--worktree"],
        description="Name of a specific worktree to fetch changes for.",
        nargs="?",
    )

    def run(self):
        changes_by_worktree = self.grouped_changes()
        sorted_worktree: list[str] = sorted(
            changes_by_worktree.keys(),
            key=lambda worktree: (
                -int(worktree.partition(".")[0]) if worktree[0].isdigit() else -float("inf"),
                worktree,
            ),
        )

        self.print()

        for worktree in sorted_worktree:
            self.run_hook(worktree, changes_by_worktree[worktree])

        self.console.clear_line()

    def run_hook(self, worktree: str, changes: list[tuple[str, int, int]]):
        """Print a summary of the pending changes for a worktree."""
        self.table(
            [
                TableHeader("Repository", min_width=max(len(repository.name) for repository in self.repositories)),
                TableHeader("Behind", align="right"),
                TableHeader("Ahead", align="right"),
            ],
            [
                [
                    repository,
                    str(behind) if not behind else string.stylize(str(behind), "color.red"),
                    str(ahead) if not ahead else string.stylize(str(ahead), "color.red"),
                ]
                for repository, behind, ahead in changes
            ],
            title=worktree,
        )

    @lru_cache  # noqa: B019
    def grouped_changes(self) -> dict[str, list[tuple[str, int, int]]]:
        """Group changes by version."""
        changes: dict[str, list[tuple[str, int, int]]] = {}

        for repository in self.repositories:
            repository.fetch(detached=False)

        for name, worktrees in self.grouped_worktrees.items():
            if self.args.worktree and self.args.worktree != name:
                continue

            for worktree in worktrees:
                changes.setdefault(name, []).append((worktree.connector.name, *worktree.pending_changes()))

        if not changes:
            if self.args.worktree:
                raise self.error(f"Worktree with name {self.args.name!r} does not exist")
            raise self.error("No worktrees found")

        return changes
