"""Clone the Git repository for a database."""

from odev.common.commands import DatabaseCommand
from odev.common.connectors import GitConnector
from odev.common.databases import SaasDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class CloneCommand(DatabaseCommand):
    """Find the repository for a database and clone it locally."""

    name = "clone"

    arguments = [
        {
            "name": "branch",
            "help": "Single branch to checkout.",
        },
    ]

    def run(self):
        if not self.database.repository:
            if isinstance(self.database, SaasDatabase):
                self.database._select_repository_branch()

        if not self.database.repository:
            raise self.error(f"No repository found for database {self.database.name!r}")

        git = GitConnector(self.database.repository.full_name)
        git.clone(branch=self.args.branch or None)

        if not git.path.exists():
            raise self.error(f"Failed to clone repository {git.name!r}")
