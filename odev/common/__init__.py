"""Common utilities for odev."""

import pkgutil
from importlib import import_module
from pathlib import Path
from typing import cast


# --- Import helper submodules -------------------------------------------------

from . import actions
from . import arguments as args
from . import bash
from . import config
from . import console
from . import debug
from . import logging
from . import odev
from . import odoobin
from . import postgres
from . import progress
from . import python
from . import signal_handling
from . import string
from . import thread
from . import version


# --- Load plugins' helpers ----------------------------------------------------

odev_path = Path(__file__).parents[1]

plugins = [path for path in (odev_path / "plugins").glob("*/common") if path.is_dir()]
modules = pkgutil.iter_modules([directory.as_posix() for directory in plugins])

for module_info in modules:
    module_path = cast(str, module_info.module_finder.path).replace(str(odev_path.parent) + "/", "").replace("/", ".")  # type: ignore [union-attr]
    module = import_module(f"{module_path}.{module_info.name}")


# --- Setup the framework and make it globally available -----------------------


global framework
framework = None


def init_framework():
    """Initialize the framework once."""
    global framework
    if framework is None:
        framework = odev.Odev()
    return framework
