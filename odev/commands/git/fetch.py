"""Fetch changes in local worktrees."""

from typing import (
    Any,
    Generator,
    List,
    MutableMapping,
    Tuple,
)

from odev.common import args, progress, string
from odev.common.commands import Command
from odev.common.connectors import GitConnector
from odev.common.console import Colors
from odev.common.logging import logging
from odev.common.odoobin import ODOO_COMMUNITY_REPOSITORIES, ODOO_ENTERPRISE_REPOSITORIES
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)

TABLE_HEADERS: List[MutableMapping[str, Any]] = [
    {
        "name": "Repositories",
        "min_width": max(len(repository) for repository in ODOO_COMMUNITY_REPOSITORIES + ODOO_ENTERPRISE_REPOSITORIES),
    },
    {"name": "Commits Behind", "justify": "right"},
    {"name": "Commits Ahead", "justify": "right"},
]


class FetchCommand(Command):
    """Fetch changes in local Odoo worktrees managed by odev."""

    name = "fetch"

    version = args.String(aliases=["-V", "--version"], description="Fetch changes for a specific Odoo version only.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        for repository in ODOO_COMMUNITY_REPOSITORIES + ODOO_ENTERPRISE_REPOSITORIES:
            git = GitConnector(repository)

            if not git.exists:
                continue

            for worktree in git.worktrees():
                if self.args.version and OdooVersion(worktree.branch) != OdooVersion(self.args.version):
                    continue

                with progress.spinner(f"Fetching changes in {repository!r} for version {worktree.branch!r}"):
                    worktree.repository.remotes.origin.fetch()
                    behind, ahead = worktree.pending_changes()
                    yield repository, worktree.branch, behind, ahead

                logger.info(f"Repository {repository!r} correctly updated for version {worktree.branch!r}")

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

    def print_table(self, rows: List[List[str]], name: str = None, style: str = None):
        """Print a table.
        :param rows: The table rows.
        :param name: The table name.
        :type rows: List[List[str]]
        """
        self.print()

        if name is not None:
            if style is None:
                style = f"bold {Colors.CYAN}"

            rule_char: str = "─"
            title: str = f"{rule_char} [{style}]{name}[/{style}]"
            self.console.rule(title, align="left", style="", characters=rule_char)

        self.table([{**header} for header in TABLE_HEADERS], rows, show_header=True, box=None)
