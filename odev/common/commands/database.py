import inspect
import re
from abc import ABC
from argparse import Namespace
from typing import (
    ClassVar,
    Mapping,
    Optional,
    Sequence,
    Union,
)

from odev.common import progress, string
from odev.common.commands import Command
from odev.common.databases import LocalDatabase, SaasDatabase
from odev.common.errors import CommandError
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DatabaseType = Union[LocalDatabase, SaasDatabase]


class DatabaseCommand(Command, ABC):
    """Base class for commands that require a database to work."""

    _database_arg_required: ClassVar[bool] = True
    """Whether the command requires a database to be specified or not in its arguments."""

    _database_exists_required: ClassVar[bool] = True
    """Whether the database must exist before running the command."""

    _database_platforms: ClassVar[Mapping[str, type[DatabaseType]]] = {
        "local": LocalDatabase,
    }

    _database_allowed_platforms: ClassVar[Sequence[str]] = []
    """The list of allowed database platforms for this command.
    An empty sequence means all platforms are allowed.
    """

    arguments = [
        {
            "name": "database",
            "help": "The database to target.",
        },
        {
            "name": "platform",
            "aliases": ["-p", "--platform"],
            "help": f"""
            Force searching for the database on the specified platform, useful when
            different databases have the same name on different hosting (usually one
            local database being a copy of a remote one). One of {string.join_or(list(_database_platforms.keys()))}.
            """,
            "choices": list(_database_platforms.keys()),
        },
        {
            "name": "branch",
            "aliases": ["-b", "--branch"],
            "help": """
            The branch to target, only used with PaaS (Odoo SH) databases
            to force using a specific branch after project detection.
            """,
        },
    ]

    database: Optional[DatabaseType] = None
    """The database instance associated with the command."""

    def __init__(self, args: Namespace, database: DatabaseType = None, **kwargs):
        super().__init__(args, **kwargs)
        self.database_name: Optional[str] = self.args.database or None
        """The database name specified by the user."""

        if database is not None:
            self.database = database
        elif self._database_arg_required or self.database_name is not None:
            self.database = self.infer_database_instance()

        if self._database_exists_required:
            if self.database is None:
                raise self.error("No database specified")
            if not self.database.exists:
                raise self.error(f"Database {self.database.name!r} does not exist")

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        if not cls._database_allowed_platforms:
            cls._database_allowed_platforms = list(cls._database_platforms.keys())

        if not cls._database_arg_required:
            cls.update_argument("database", {"nargs": "?"})

    def infer_database_instance(self) -> Optional[DatabaseType]:
        """Return the database instance to use with this command, inferred from the database's name."""
        if not self.database_name:
            return None

        if hasattr(self.args, "platform") and self.args.platform:
            allowed_database_classes = [self._database_platforms[self.args.platform]]
        else:
            allowed_database_classes = [
                DatabaseClass
                for key, DatabaseClass in self._database_platforms.items()
                if key in self._database_allowed_platforms
            ]

        for DatabaseClass in allowed_database_classes:
            with progress.spinner(
                f"Searching for existing {DatabaseClass._platform_display} database {self.database_name!r}"
            ):
                database: DatabaseType

                if "branch" in inspect.getfullargspec(DatabaseClass.__init__).args and self.args.branch:
                    database = DatabaseClass(self.database_name, branch=self.args.branch)  # type: ignore [call-arg]
                else:
                    database = DatabaseClass(self.database_name)

                if database.exists:
                    logger.debug(f"Found existing {DatabaseClass._platform_display} database {database.name!r}")
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


class LocalDatabaseCommand(DatabaseCommand):
    """Base class for commands that require a local database to work."""

    database: LocalDatabase

    _database_allowed_platforms = ["local"]

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # Remove arguments from the `DatabaseCommand` class that are not relevant
        # for this command (`branch` is only used for PaaS databases)
        cls.remove_argument("platform")
        cls.remove_argument("branch")


class SaasDatabaseCommand(DatabaseCommand):
    """Base class for commands that require a SaaS database to work."""

    database: SaasDatabase

    _database_allowed_platforms = ["saas"]

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # Remove arguments from the `DatabaseCommand` class that are not relevant
        # for this command (`branch` is only used for PaaS databases)
        cls.remove_argument("platform")
        cls.remove_argument("branch")
