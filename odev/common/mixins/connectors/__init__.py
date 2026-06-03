"""Connector mixins."""

import pkgutil
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import cast
from inspect import isclass

# --- Common modules -----------------------------------------------------------
from .base import ConnectorMixin, ensure_connected
from .github import GitConnectorMixin
from .postgres import PostgresConnectorMixin


# --- Plugins ------------------------------------------------------------------
from odev.common.config import CONFIG_DIR
plugins_path = CONFIG_DIR / "plugins"

odev_module = sys.modules.get("odev")
if not hasattr(odev_module, "plugins"):
    odev_module.plugins = ModuleType("odev.plugins")
    odev_module.plugins.__path__ = [str(plugins_path)]
    sys.modules["odev.plugins"] = odev_module.plugins

plugins = [path for path in plugins_path.glob("*/common/mixins/*") if path.is_dir()]
modules = pkgutil.iter_modules([directory.as_posix() for directory in plugins])

for module_info in modules:
    module_path = cast(str, module_info.module_finder.path).replace(str(plugins_path) + "/", "").replace("/", ".")  # type: ignore [union-attr]
    module = import_module(f"odev.plugins.{module_path}.{module_info.name}")

    for attribute in dir(module):
        obj = getattr(module, attribute)

        if isclass(obj) and issubclass(obj, ConnectorMixin) and obj is not ConnectorMixin:
            globals()[attribute] = obj
