from odev.common import args, progress
from odev.common.commands import GitCommand, LocalDatabaseCommand
from odev.common.connectors import GitConnector
from odev.common.logging import logging
from odev.common.python import PythonEnv


logger = logging.getLogger(__name__)


class DatabaseSetCommand(LocalDatabaseCommand, GitCommand):
    """Edit local databases' parameters."""

    _name = "database"
    _aliases = ["db"]

    set_repository = args.String(
        aliases=["--set-repo"],
        description="Change the repository linked to the database, in the format <organization>/<repository>.",
        metavar="REPOSITORY",
    )
    remove_repository = args.Flag(
        aliases=["--remove-repo"],
        description="Remove the repository linked to the database.",
    )

    set_venv = args.String(
        aliases=["--set-venv"],
        description="Change the virtualenv linked to the database.",
        metavar="VENV",
    )
    remove_venv = args.Flag(
        aliases=["--remove-venv"],
        description="Remove the virtualenv linked to the database.",
    )

    set_worktree = args.String(
        aliases=["--set-worktree"],
        description="Change the worktree linked to the database.",
        metavar="WORKTREE",
    )
    remove_worktree = args.Flag(
        aliases=["--remove-worktree"],
        description="Remove the worktree linked to the database.",
    )

    whitelist = args.FlagOptional(
        aliases=["--whitelist"],
        description="Whitelist or unwhitelist the database.",
    )

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        cls.remove_argument("version")

    def run(self):
        self.args.version = None

        with progress.spinner("Setting database parameters"):
            self._set_values()
            self._remove_values()

    def _set_values(self):
        if self.args.set_repository:
            repo = GitConnector(self.args.set_repository)

            if not repo.exists and self.console.confirm("Repository not found locally, clone now?"):
                self.odev.run_command("clone", repo.name)

            self.store.databases.set_value(self._database, "repository", f"{self.args.set_repository!r}")
            self.store.databases.set_value(self._database, "branch", "NULL")
            logger.info(f"Repository set to {self.args.set_repository!r}")

        if self.args.set_venv:
            venv = PythonEnv(self.args.set_venv)

            if venv.exists:
                self.store.databases.set_value(self._database, "virtualenv", f"{self.args.set_venv!r}")
                logger.info(f"Virtualenv set to {self.args.set_venv!r}")
            else:
                logger.error(f"Virtualenv {self.args.set_venv!r} not found, please create it and retry")

        if self.args.set_worktree:
            if self.args.set_worktree in self.grouped_worktrees:
                self.store.databases.set_value(self._database, "worktree", f"{self.args.set_worktree!r}")
                logger.info(f"Worktree set to {self.args.set_worktree!r}")
            else:
                logger.error(f"Worktree {self.args.set_worktree!r} not found, please create it and retry")

        if self.args.whitelist is True:
            self.store.databases.set_value(self._database, "whitelisted", "TRUE")
            logger.info("Database whitelisted")

    def _remove_values(self):
        if self.args.remove_repository:
            self.store.databases.set_value(self._database, "repository", "NULL")
            self.store.databases.set_value(self._database, "branch", "NULL")
            logger.info("Repository removed")

        if self.args.remove_venv:
            self.store.databases.set_value(self._database, "virtualenv", "NULL")
            logger.info("Virtualenv removed")

        if self.args.remove_worktree:
            self.store.databases.set_value(self._database, "worktree", "NULL")
            logger.info("Worktree removed")

        if self.args.whitelist is False:
            self.store.databases.set_value(self._database, "whitelisted", "FALSE")
            logger.info("Database unwhitelisted")
