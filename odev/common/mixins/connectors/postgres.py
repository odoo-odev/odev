"""Mixins for commands that need to use a connection to a local PostgreSQL database."""

from odev.common.connectors import PostgresConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class PostgresConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a PostgreSQL connector."""

    _connector_class: type[PostgresConnector] = PostgresConnector  # type: ignore [assignment]
    connector: PostgresConnector  # type: ignore [assignment]

    def psql(self, name: str = "postgres") -> PostgresConnector:
        """Return a PostgreSQL connector to the selected database."""
        return self._connector_class(name)
