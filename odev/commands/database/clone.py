"""Clone the Git repository for a database."""

from odev.common.commands import DatabaseCommand
from odev.common.connectors import GitConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class CloneCommand(DatabaseCommand):
    """Find the repository for a database and clone it locally."""

    name = "clone"

    arguments = [
        {
            "name": "branch",
            "help": "Branch to checkout after cloning the repository.",
        },
    ]

    def run(self):
        if not self.database.repository:
            raise self.error(f"No repository found for database {self.database.name!r}")

        git = GitConnector(self.database.repository.full_name)

        if git.path.exists():
            git.checkout(branch=self.args.branch or None)
        else:
            git.clone(branch=self.args.branch or None)

        if not git.path.exists():
            raise self.error(f"Failed to clone repository {git.name!r}")
