"""Clone the Git repository for a database."""

from odev.common import args
from odev.common.commands import DatabaseCommand
from odev.common.commands.database import DatabaseType
from odev.common.connectors import GitConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class CloneCommand(DatabaseCommand):
    """Clone a GitHub repository locally, under the path managed by odev. A database name can be passed instead
    of a repository address to find and clone the repository linked to that database.
    """

    name = "clone"

    repository = args.String(description="Git URL of a repository to clone.", nargs="?")
    branch = args.String(description="Branch to checkout after cloning the repository.")

    _database_arg_required = False
    _database_exists_required = False

    def infer_database_instance(self) -> DatabaseType | None:
        if any(char in self.args.database for char in "@:"):
            self.args.repository = self.args.database
            self.args.database = None
            return None

        return super().infer_database_instance()

    def run(self):
        if not self.args.database and not self.args.repository:
            raise self.error("You must specify a database or repository to clone")

        if self.args.database and self.args.repository:
            raise self.error("You cannot specify both a database and a repository to clone")

        git = GitConnector(self.database.repository.full_name if self.database is not None else self.args.repository)

        if git.path.exists():
            git.checkout(branch=self.args.branch or None)
        else:
            git.clone(branch=self.args.branch or None)

        if not git.path.exists():
            raise self.error(f"Failed to clone repository {git.name!r}")
