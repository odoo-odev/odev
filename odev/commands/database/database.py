"""Edit the parameters of a local database without starting it."""

from odev.common import args, string
from odev.common.commands import GitCommand, LocalDatabaseCommand
from odev.common.connectors import GitConnector
from odev.common.errors import ConnectorError
from odev.common.logging import logging
from odev.common.python import PythonEnv


logger = logging.getLogger(__name__)


class DatabaseSetCommand(LocalDatabaseCommand, GitCommand):
    """Display and edit the parameters of a local database without starting it.
    Called without any argument other than the database, the current parameters are displayed.
    """

    _name = "database"
    _aliases = ["db"]

    set_repository = args.String(
        aliases=["--set-repo"],
        description="""Change the repository linked to the database. Accepts a repository name in
        the format <organization>/<repository>, a git URL or the path to a local clone.
        """,
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
        description="Whitelist or unwhitelist the database, preventing or allowing its automatic removal.",
    )

    _exclusive_pairs = (
        ("set_repository", "remove_repository"),
        ("set_venv", "remove_venv"),
        ("set_worktree", "remove_worktree"),
    )
    """Pairs of arguments that set and remove the same value, and cannot be used together."""

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        cls.remove_argument("version")

    def run(self):
        self._check_exclusive_arguments()

        if self._has_changes:
            self._set_values()
            self._remove_values()

        self._print_values()

    @property
    def _has_changes(self) -> bool:
        """Whether the command was called with an argument changing a parameter."""
        return bool(
            self.args.set_repository
            or self.args.remove_repository
            or self.args.set_venv
            or self.args.remove_venv
            or self.args.set_worktree
            or self.args.remove_worktree
            or self.args.whitelist is not None
        )

    def _check_exclusive_arguments(self) -> None:
        """Ensure no parameter is both set and removed in the same call."""
        for set_argument, remove_argument in self._exclusive_pairs:
            if getattr(self.args, set_argument) and getattr(self.args, remove_argument):
                raise self.error(
                    f"Arguments {self.argument_name(set_argument)!r} and "
                    f"{self.argument_name(remove_argument)!r} cannot be used together"
                )

    def argument_name(self, argument: str) -> str:
        """Return the CLI alias of an argument, for use in error messages."""
        aliases = self._arguments.get(argument, {}).get("aliases", [])
        return next((alias for alias in aliases if alias.startswith("--")), argument)

    def _set_values(self) -> None:
        if self.args.set_repository:
            self._set_repository(self.args.set_repository)

        if self.args.set_venv:
            venv = PythonEnv(self.args.set_venv)

            if not venv.exists:
                raise self.error(f"Virtualenv {self.args.set_venv!r} not found, please create it and retry")

            self._database.venv = venv
            logger.info(f"Virtualenv set to {venv.name!r}")

        if self.args.set_worktree:
            if self.args.set_worktree not in self.grouped_worktrees:
                raise self.error(f"Worktree {self.args.set_worktree!r} not found, please create it and retry")

            self._database.worktree = self.args.set_worktree
            logger.info(f"Worktree set to {self.args.set_worktree!r}")

        if self.args.whitelist is True:
            self._database.whitelisted = True
            logger.info("Database whitelisted")

    def _set_repository(self, repository: str) -> None:
        """Link a repository to the database, cloning it first if it is missing locally.

        :param repository: The repository name, git URL or path to a local clone.
        """
        try:
            connector = GitConnector(repository)
        except ConnectorError as error:
            raise self.error(str(error)) from error

        if not connector.exists and self.console.confirm(
            f"Repository {connector.name!r} not found locally, clone now?"
        ):
            self.odev.run_command("clone", connector.name)

        linked = self._database.link_repository(connector)
        logger.info(f"Repository set to {linked.full_name!r}")

    def _remove_values(self) -> None:
        # Values are cleared through the data store rather than through the database properties:
        # those fall back to reading the store when their cached value is empty, so assigning None
        # to them would write the value that was just cleared straight back.
        if self.args.remove_repository:
            self.store.databases.set_value(self._database, "repository", None)
            self.store.databases.set_value(self._database, "branch", None)
            self._database._repository = None
            self._database._branch = None
            logger.info("Repository removed")

        if self.args.remove_venv:
            self.store.databases.set_value(self._database, "virtualenv", None)
            self._database._venv = None
            logger.info("Virtualenv removed")

        if self.args.remove_worktree:
            self.store.databases.set_value(self._database, "worktree", None)
            self._database._worktree = None
            logger.info("Worktree removed")

        if self.args.whitelist is False:
            self._database.whitelisted = False
            logger.info("Database unwhitelisted")

    def _print_values(self) -> None:
        """Print the current parameters of the database."""
        info = self.store.databases.get(self._database)
        values = {
            "Repository": info and info.repository,
            "Branch": info and info.branch,
            "Virtualenv": info and info.virtualenv,
            "Worktree": info and info.worktree,
            "Whitelisted": "yes" if info and info.whitelisted else "no",
        }
        logger.info(
            f"Parameters of database {self._database.name!r}:\n"
            + string.join_bullet([f"{key}: {value or 'not set'}" for key, value in values.items()])
        )
