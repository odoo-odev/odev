"""Fetch changes in local worktrees."""

from typing import Generator, List, MutableMapping, Tuple

from git import GitCommandError

from odev.common import args, progress, string
from odev.common.commands import GitCommand
from odev.common.console import Colors
from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class FetchCommand(GitCommand):
    """Fetch changes in local Odoo worktrees managed by odev."""

    _name = "fetch"

    version = args.String(aliases=["-V", "--version"], description="Fetch changes for a specific Odoo version only.")

    def run(self):
        """Run the command."""
        changes_by_version = self.pending_changes_by_version()
        sorted_versions: List[str] = sorted(
            changes_by_version.keys(),
            key=lambda version: (int(version.partition(".")[0]) if version[0].isdigit() else float("inf"), version),
        )

        for version in sorted_versions:
            self.print_table(
                [
                    [
                        repository,
                        str(behind) if not behind else string.stylize(str(behind), Colors.RED),
                        str(ahead) if not ahead else string.stylize(str(ahead), Colors.RED),
                    ]
                    for repository, behind, ahead in sorted(
                        changes_by_version[version],
                        key=lambda repository: repository[0],
                    )
                ],
                version,
            )

    def list_pending_changes(self) -> Generator[Tuple[str, str, int, int], None, None]:
        """List pending changes in local repositories."""
        for worktree in self.worktrees:
            with progress.spinner(f"Fetching changes in {worktree.connector.name!r} for version {worktree.branch!r}"):
                try:
                    worktree.repository.remotes.origin.fetch()
                    behind, ahead = worktree.pending_changes()
                    yield worktree.connector.name, worktree.branch, behind, ahead
                except GitCommandError as error:
                    logger.error(
                        f"Failed to fetch changes in {worktree.connector.name!r} for version {worktree.branch!r}"
                        f":\n{error.args[2].decode()}"
                    )
                    continue

            logger.info(f"Changes fetched in repository {worktree.connector.name!r} for version {worktree.branch!r}")

    def pending_changes_by_version(self) -> MutableMapping[str, List[Tuple[str, int, int]]]:
        """List pending changes by version."""
        changes: MutableMapping[str, List[Tuple[str, int, int]]] = {}

        for repository, branch, behind, ahead in self.list_pending_changes():
            changes.setdefault(branch, []).append((repository, behind, ahead))

        if not changes:
            if self.args.version:
                raise self.error(f"No worktrees found for version {str(OdooVersion(self.args.version))!r}")
            raise self.error("No worktrees found")

        return changes
