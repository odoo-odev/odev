"""Connectors to external services."""

from typing import TYPE_CHECKING

from odev.common.lazy import lazy_exports


# Declared for type checkers and IDEs only: at runtime the names below are resolved by `__getattr__`, so that
# importing this package does not import every connector it exposes.
if TYPE_CHECKING:
    from odev.common.connectors.base import Connector
    from odev.common.connectors.git import GitConnector, GithubConnector, GitWorktree, Stash
    from odev.common.connectors.postgres import PostgresConnector
    from odev.common.connectors.rest import RestConnector
    from odev.common.connectors.rpc import RpcConnector

__all__ = [
    "Connector",
    "GitConnector",
    "GitWorktree",
    "GithubConnector",
    "PostgresConnector",
    "RestConnector",
    "RpcConnector",
    "Stash",
]

__getattr__ = lazy_exports(
    __name__,
    {
        "Connector": "base",
        "GitConnector": "git",
        "GithubConnector": "git",
        "GitWorktree": "git",
        "Stash": "git",
        "PostgresConnector": "postgres",
        "RestConnector": "rest",
        "RpcConnector": "rpc",
    },
)
