from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from odev.common.commands.base import Command


class CommandError(Exception):
    """Custom exception for errors raised during commands execution."""

    def __init__(self, command: "Command", *args, **kwargs):
        """
        Initialize the exception.

        :param command: the command that raised the exception
        """
        super().__init__(*args, **kwargs)
        self.command: "Command" = command
