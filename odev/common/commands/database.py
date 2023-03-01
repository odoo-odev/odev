import re
from abc import ABC
from typing import ClassVar, Optional, Union

from odev.common.commands import Command
from odev.common.databases import LocalDatabase, SaasDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class DatabaseCommand(Command, ABC):
    """Base class for commands that require a database to work."""

    _database_arg_required: ClassVar[bool] = True
    """Whether the command requires a database to be specified or not in its arguments."""

    arguments = [
        {
            "name": "database",
            "help": "The database to target.",
        },
    ]

    _require_exists: bool = True
    """Whether the database must exist before running the command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.database_name: Optional[str] = self.args.database or None
        """The database name specified by the user."""

        self.database: Optional[Union[LocalDatabase, SaasDatabase]] = self.infer_database_instance()
        """The database instance associated with the command."""

        if self._require_exists and not self.database.exists:
            raise self.error(f"Database {self.database.name!r} does not exist.")

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        if not cls._database_arg_required:
            cls.update_argument("database", {"nargs": "?"})

    def infer_database_instance(self) -> Optional[Union[LocalDatabase, SaasDatabase]]:
        """Return the database instance to use with this command, inferred from the database's name."""
        if not self.database_name:
            return None

        for database_cls in (
            LocalDatabase,
            SaasDatabase,
        ):
            database = database_cls(self.database_name)

            if database.exists:
                logger.debug(f"Found existing {database_cls.__name__} {database!r}")
                return database

        if re.match(r"^[a-z0-9][a-z0-9$_.-]+$", self.database_name, re.IGNORECASE):
            logger.debug(f"Falling back to non-existing {LocalDatabase.__name__} {self.database_name!r}")
            return LocalDatabase(self.database_name)

        raise ValueError(f"Could not determine database type from name: {self.database_name!r}")
