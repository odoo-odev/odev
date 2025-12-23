"""Clone the Git repository for a database."""

from odev.common import args
from odev.common.commands import DatabaseOrRepositoryCommand
from odev.common.connectors import GitConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class CloneCommand(DatabaseOrRepositoryCommand):
    """Clone a GitHub repository locally, under the path managed by odev. A database name can be passed instead
    of a repository address to find and clone the repository linked to that database.
    """

    _name = "clone"

    branch = args.String(description="Branch to checkout after cloning the repository.")

    def run(self):
        if not self.args.database and not self.args.repository:
            raise self.error("You must specify a database or repository to clone")

        if self.args.database and self.args.repository:
            raise self.error("You cannot specify both a database and a repository to clone")

        if not self.__check_repository():
            raise self.error("No repository found to clone")

        self._clone_repository()

    def _clone_repository(self):
        """Find and clone the correct repository."""
        git = GitConnector(self.args.repository or self._database.repository.full_name)

        if git.path.exists():
            logger.info(f"Repository {git.name!r} already cloned under {git.path.as_posix()}")
            git.checkout(revision=self.args.branch or None)
        else:
            git.clone(revision=self.args.branch or None)

        if not git.path.exists():
            raise self.error(f"Failed to clone repository {git.name!r}")

    def __check_repository(self):
        """Check if a repository is available to clone."""
        return self.args.repository or self._database.repository is not None
