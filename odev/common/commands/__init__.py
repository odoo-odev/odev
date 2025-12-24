"""Odev base command classes."""

from typing import TypeVar

from .base import Command, CommandError
from .database import DatabaseCommand, DatabaseOrRepositoryCommand, LocalDatabaseCommand, RemoteDatabaseCommand
from .git import GitCommand
from .odoobin import (
    TEMPLATE_SUFFIX,
    OdoobinCommand,
    OdoobinShellCommand,
    OdoobinShellScriptCommand,
    OdoobinTemplateCommand,
)

CommandType = TypeVar("CommandType", Command, DatabaseCommand)

__all__ = [
    "TEMPLATE_SUFFIX",
    "Command",
    "CommandError",
    "CommandType",
    "DatabaseCommand",
    "DatabaseOrRepositoryCommand",
    "GitCommand",
    "LocalDatabaseCommand",
    "OdoobinCommand",
    "OdoobinShellCommand",
    "OdoobinShellScriptCommand",
    "OdoobinTemplateCommand",
    "RemoteDatabaseCommand",
]
