"""Odev base command classes."""

from typing import TypeVar

from .base import Command, CommandError
from .database import (
    DatabaseCommand,
    LocalDatabaseCommand,
    PaasDatabaseCommand,
    SaasDatabaseCommand,
)
from .odoobin import (
    OdoobinCommand,
    OdoobinShellCommand,
    OdoobinShellScriptCommand,
)

CommandType = TypeVar("CommandType", Command, DatabaseCommand)
