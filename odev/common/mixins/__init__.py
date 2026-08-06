"""Mixins to extend the functionality of command classes."""

from typing import TYPE_CHECKING

from odev.common.lazy import lazy_exports


# Declared for type checkers and IDEs only: at runtime the names below are resolved by `__getattr__`, so that
# importing this package does not import the connectors the mixins wrap.
if TYPE_CHECKING:
    from odev.common.mixins.connectors.base import ConnectorMixin, ensure_connected
    from odev.common.mixins.connectors.github import GitConnectorMixin
    from odev.common.mixins.connectors.postgres import PostgresConnectorMixin
    from odev.common.mixins.databases.list import ListLocalDatabasesMixin


__all__ = [
    "ConnectorMixin",
    "GitConnectorMixin",
    "ListLocalDatabasesMixin",
    "PostgresConnectorMixin",
    "ensure_connected",
]

__getattr__ = lazy_exports(
    __name__,
    {
        "ConnectorMixin": "connectors.base",
        "ensure_connected": "connectors.base",
        "GitConnectorMixin": "connectors.github",
        "PostgresConnectorMixin": "connectors.postgres",
        "ListLocalDatabasesMixin": "databases.list",
    },
)
