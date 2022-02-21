"""Command-related exception classes."""

from typing import Any, List, MutableMapping, Optional

from odev.exceptions.odev import OdevException


class CommandException(OdevException):
    """Base class for command-related exceptions."""


class CommandAborted(CommandException):
    """Raised when a command has been aborted by the user."""

    def __init__(self, message: Optional[str] = None, *args: List[Any], **kwargs: MutableMapping[str, Any]) -> None:
        message = message or "Action cancelled"
        super().__init__(message, *args, **kwargs)


class CommandMissing(CommandException):
    """Raised when `odev` is invoked with no command arguments."""


class InvalidArgument(CommandException):
    """Raised when command arguments cannot be parsed or used."""


class InvalidQuery(CommandException):
    """Raised when an error occurred while running SQL queries on a database."""
