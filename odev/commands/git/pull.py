"""Pull changes in local worktrees."""

from typing import Any, List, MutableMapping

from odev.common import progress
from odev.common.commands import Command
from odev.common.connectors import GitConnector
from odev.common.logging import logging
from odev.common.odoo import ODOO_COMMUNITY_REPOSITORIES, ODOO_ENTERPRISE_REPOSITORIES
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


class PullCommand(Command):
    """Pull changes in local worktrees."""

    name = "pull"

    arguments = [
        {
            "name": "version",
            "aliases": ["-V", "--version"],
            "help": "Pull changes for a specific Odoo version only.",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self):
        for repository in ODOO_COMMUNITY_REPOSITORIES + ODOO_ENTERPRISE_REPOSITORIES:
            git = GitConnector(repository)

            if not git.exists:
                continue

            for worktree in git.worktrees():
                if self.args.version and OdooVersion(worktree.branch) != OdooVersion(self.args.version):
                    continue

                behind, _ = worktree.pending_changes()

                if not behind:
                    continue

                with progress.spinner(f"Pulling {behind} commits in {repository!r} for version {worktree.branch!r}"):
                    git.pull_worktrees([worktree], force=True)
                    logger.info(f"Pulled {behind} commits in {repository!r} for version {worktree.branch!r}")

        logger.info("Worktrees are up-to-date")
