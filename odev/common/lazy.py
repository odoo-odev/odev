"""Helpers to re-export names from a package without importing their module eagerly."""

import sys
from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any


__all__ = ["lazy_exports"]


def lazy_exports(package: str, exports: Mapping[str, str]) -> Callable[[str], Any]:
    """Build the `__getattr__` of a package re-exporting names from its submodules.

    Importing a package should not drag in every module it re-exports: the connectors alone pull in a GitHub API
    client, an RPC client and a database driver, none of which most commands ever touch. Names are instead resolved
    the first time they are accessed, then cached on the package so subsequent accesses are plain lookups.

    :param package: Name of the package the names are re-exported from, usually its `__name__`.
    :param exports: Mapping of each re-exported name to the submodule defining it, relative to the package.
    :return: A function to assign to the package's `__getattr__`.
    :rtype: Callable[[str], Any]
    """

    def resolve(name: str) -> Any:
        module = exports.get(name)

        if module is None:
            raise AttributeError(f"module {package!r} has no attribute {name!r}")

        value = getattr(import_module(f"{package}.{module}"), name)
        setattr(sys.modules[package], name, value)

        return value

    return resolve
