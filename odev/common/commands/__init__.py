"""Odev base command classes."""

import pkgutil
from importlib import import_module
from pathlib import Path
from typing import cast


# --- Common modules -----------------------------------------------------------

from typing import TypeVar

from .base import Command, CommandError
from .database import DatabaseCommand, LocalDatabaseCommand, RemoteDatabaseCommand, DatabaseOrRepositoryCommand
from .git import GitCommand
from .odoobin import (
    OdoobinCommand,
    OdoobinTemplateCommand,
    OdoobinShellCommand,
    OdoobinShellScriptCommand,
    TEMPLATE_SUFFIX,
)


# --- Plugins ------------------------------------------------------------------

odev_path = Path(__file__).parent.parent.parent

plugins = [path for path in (odev_path / "plugins").glob("*/common/commands") if path.is_dir()]
modules = pkgutil.iter_modules([directory.as_posix() for directory in plugins])

for module_info in modules:
    module_path = cast(str, module_info.module_finder.path).replace(str(odev_path.parent) + "/", "").replace("/", ".")  # type: ignore [union-attr]
    module = import_module(f"{module_path}.{module_info.name}")

    for attribute in dir(module):
        obj = getattr(module, attribute)

        if isinstance(obj, type) and issubclass(obj, Command) and obj is not Command:
            globals()[attribute] = obj


CommandType = TypeVar("CommandType", Command, DatabaseCommand)
