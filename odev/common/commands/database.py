import re
from abc import ABC
from typing import ClassVar, Optional

from odev.common.commands import Command
from odev.common.databases import LocalDatabase


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

        self.database: Optional[LocalDatabase] = self.get_database_from_name()
        """The database instance associated with the command."""

        if self._require_exists and not self.database.exists:
            raise self.error(f"Database {self.database.name!r} does not exist.")

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        if not cls._database_arg_required:
            cls.update_argument("database", {"nargs": "?"})

    def get_database_from_name(self) -> Optional[LocalDatabase]:
        """Return the database instance associated with the command."""
        if not self.database_name:
            return None

        if re.match(r"^[a-z0-9][a-z0-9$_.-]+$", self.database_name, re.IGNORECASE):
            return LocalDatabase(self.database_name)

        raise ValueError(f"Could not determine database type from name: {self.database_name!r}")
