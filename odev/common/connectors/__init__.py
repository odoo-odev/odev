"""Connectors to external services."""

import pkgutil
from importlib import import_module
from pathlib import Path
from typing import cast


# --- Common modules -----------------------------------------------------------

from .base import Connector
from .postgres import PostgresConnector
from .rest import RestConnector
from .git import GitConnector, GitWorktree, Stash
from .rpc import RpcConnector
from .saas import SaasConnector


# --- Plugins ------------------------------------------------------------------

plugins = [
    path for path in (Path(__file__).parent.parent.parent / "plugins").glob("*/common/connectors") if path.is_dir()
]
modules = pkgutil.iter_modules([directory.as_posix() for directory in plugins])

for module_info in modules:
    module_path = cast(str, module_info.module_finder.path).split("/odev/", 1)[1].replace("/", ".")  # type: ignore [union-attr]
    module = import_module(f"odev.{module_path}.{module_info.name}")

    for attribute in dir(module):
        obj = getattr(module, attribute)

        if isinstance(obj, type) and issubclass(obj, Connector) and obj is not Connector:
            globals()[attribute] = obj
