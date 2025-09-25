import inspect
import re
from abc import ABC
from argparse import Namespace
from collections.abc import Mapping, Sequence
from typing import ClassVar

from odev.common import args, progress, string
from odev.common.commands import Command
from odev.common.databases import DummyDatabase, LocalDatabase, RemoteDatabase
from odev.common.errors import CommandError
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DatabaseType = LocalDatabase | RemoteDatabase | DummyDatabase


class DatabaseCommand(Command, ABC):
    """Base class for commands that require a database to work."""

    _database: DatabaseType
    """The database instance associated with the command."""

    _database_arg_required: ClassVar[bool] = True
    """Whether the command requires a database to be specified or not in its arguments."""

    _database_platforms: ClassVar[Mapping[str, type[DatabaseType]]] = {
        "local": LocalDatabase,
        "remote": RemoteDatabase,
    }
    """The database hosting platforms supported by this command, in order of priority for hosting lookup
    (the first key in this ordered dictionary will be checked first).
    """

    _database_allowed_platforms: ClassVar[Sequence[str]] = []
    """The list of allowed database platforms for this command.
    An empty sequence means all platforms are allowed.
    """

    # --------------------------------------------------------------------------
    # Arguments
    # --------------------------------------------------------------------------

    target_database = args.String(name="database", description="The database to target.")
    platform = args.String(
        aliases=["-p", "--platform"],
        choices=[],
        description=f"""
        Force searching for the database on the specified platform, useful when
        different databases have the same name on different hosting (usually one
        local database being a copy of a remote one).
        One of {string.join_or(list(_database_allowed_platforms))}.
        """,
    )
    branch = args.String(
        aliases=["-b", "--branch"],
        description="""
        The branch to target, only used with PaaS (Odoo SH) databases
        to force using a specific branch after project detection.
        """,
    )

    # --------------------------------------------------------------------------

    def __init__(self, args: Namespace, database: DatabaseType | None = None, **kwargs):
        super().__init__(args, **kwargs)
        self.database_name: str | None = self.args.database or None
        """The database name specified by the user."""

        self._database: DatabaseType = DummyDatabase()

        if database is not None:
            self._database = database
        elif self._database_arg_required or self.database_name is not None:
            self._database = self.infer_database_instance()

        if self._database_exists_required:
            if isinstance(database, DummyDatabase):
                raise self.error("No database specified")
            if not self._database.exists:
                raise self.error(f"Database {self._database.name!r} does not exist")

    @property
    def _database_exists_required(self) -> bool:
        """Return True if a database has to exist for the command to work."""
        return True

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        if not cls._database_allowed_platforms:
            cls._database_allowed_platforms = list(cls._database_platforms.keys())

        if not cls._database_arg_required:
            cls.update_argument("database", nargs="?")

        cls.update_argument(
            "platform",
            choices=list(cls._database_allowed_platforms),
            description=f"""
            Force searching for the database on the specified platform, useful when
            different databases have the same name on different hosting (usually one
            local database being a copy of a remote one).
            One of {string.join_or(list(cls._database_allowed_platforms))}.
            """,
        )

    def infer_database_instance(self) -> DatabaseType:
        """Return the database instance to use with this command, inferred from the database's name."""
        if self._database.name is None:
            raise CommandError("No database specified", self)

        if hasattr(self.args, "platform") and self.args.platform:
            allowed_database_classes = [self._database_platforms[self.args.platform]]
        else:
            allowed_database_classes = [
                DatabaseClass
                for key, DatabaseClass in self._database_platforms.items()
                if key in self._database_allowed_platforms
            ]

        for database_cls in allowed_database_classes:
            with progress.spinner(
                f"Searching for existing {database_cls._platform_display} database {self.database_name!r}"
            ):
                database: DatabaseType

                if "branch" in inspect.getfullargspec(database_cls.__init__).args and self.args.branch:
                    database = database_cls(self.database_name, branch=self.args.branch)  # type: ignore [call-arg]
                else:
                    database = database_cls(self.database_name)

                if database.exists:
                    logger.debug(f"Found existing {database_cls._platform_display} database {database.name!r}")
                    return database

        if hasattr(self.args, "platform") and self.args.platform:
            raise CommandError(
                f"Could not find {allowed_database_classes[0]._platform_display} database {self.database_name!r}",
                self,
            )

        if LocalDatabase in allowed_database_classes and re.match(
            r"^[a-z0-9][a-z0-9$_.-]+$", self.database_name, re.IGNORECASE
        ):
            logger.debug(
                f"Falling back to non-existing {LocalDatabase._platform_display} database {self.database_name!r}"
            )
            return LocalDatabase(self.database_name)

        raise CommandError(f"Could not determine database type from name: {self.database_name!r}", self)


class LocalDatabaseCommand(DatabaseCommand, ABC):
    """Base class for commands that require a local database to work."""

    _database: LocalDatabase  # type: ignore [assignment]
    _database_allowed_platforms = ["local"]

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # Remove arguments from the `DatabaseCommand` class that are not relevant
        # for this command (`branch` is only used for PaaS databases)
        cls.remove_argument("platform")
        cls.remove_argument("branch")


class RemoteDatabaseCommand(DatabaseCommand, ABC):
    """Base class for commands that require a remote database to work."""

    _database: RemoteDatabase  # type: ignore [assignment]
    _database_allowed_platforms = ["remote", "paas", "saas"]


class DatabaseOrRepositoryCommand(DatabaseCommand, ABC):
    """Base class for commands that require a database or a repository to work, the first argument is interchangeable
    and we automatically infer whether the user entered a git repository or a database.
    """

    _database_arg_required = False

    repository = args.String(description="GitHub URL or name of a repository.", nargs="?")

    @property
    def _database_exists_required(self) -> bool:
        """Return True if a database has to exist for the command to work."""
        return False

    def infer_database_instance(self) -> DatabaseType:
        if any(char in self.args.database for char in "@:/"):
            self.args.repository = self.args.database
            self.args.database = None
            return DummyDatabase()

        return super().infer_database_instance()
