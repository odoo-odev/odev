from abc import ABC
from typing import ClassVar, Optional

from odev.common.commands import Command


class DatabaseCommand(Command, ABC):
    """Base class for commands that require a database to work."""

    _database_arg_required: ClassVar[bool] = True
    """Whether the command requires a database to be specified or not in its arguments."""

    arguments = [
        {
            "name": "database",
            "nargs": 1,
            "help": "The database to use.",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.database_name: Optional[str] = self.args.database or None
        """The database name specified by the user."""

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        if not cls._database_arg_required:
            cls.update_argument("database", {"nargs": "?"})
