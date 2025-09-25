from typing import TYPE_CHECKING

from .odev import OdevError


if TYPE_CHECKING:
    from odev.common.commands.base import Command


class CommandError(OdevError):
    """Custom exception for errors raised during commands execution."""

    def __init__(self, message: str, command: "Command", *args, **kwargs):
        """Initialize the exception.

        :param command: the command that raised the exception
        """
        super().__init__(message, *args, **kwargs)
        self.command: Command = command
