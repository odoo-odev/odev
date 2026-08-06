"""Mixins for commands that need to use a connection to a local PostgreSQL database."""

from odev.common.connectors import PostgresConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class PostgresConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a PostgreSQL connector."""

    _connector_class: type[PostgresConnector] = PostgresConnector  # type: ignore [assignment]
    connector: PostgresConnector  # type: ignore [assignment]

    _connection_depth: int = 0
    """Number of nested blocks currently sharing the connector."""

    def psql(self, name: str = "postgres") -> PostgresConnector:
        """Return a PostgreSQL connector to the selected database."""
        return self._connector_class(name)

    def _enter_connector(self, name: str) -> PostgresConnector:
        """Connect to a database, or join the connection an enclosing block already opened.

        `ensure_connected` runs every database method inside its own block, and those blocks nest, so
        opening a connection per block would mean a new PostgreSQL backend for each call.

        :param name: The name of the database to connect to.
        :return: The connector the caller should use.
        :rtype: PostgresConnector
        """
        # A held connection that was closed in the meantime is replaced rather than reused: `drop`
        # disconnects explicitly, and the datastore holds its own connection across such a call. At depth
        # zero the check is skipped, `connector` still being the connector class rather than an instance.
        if not self._connection_depth or not self.connector.connected:
            # Narrows what the base mixin types as a `Connector`, deliberately: everything reached through
            # this mixin talks to PostgreSQL, and its callers query rather than use the base interface.
            self.connector = self.psql(name).__enter__()  # pyright: ignore[reportIncompatibleVariableOverride]

        self._connection_depth += 1

        return self.connector

    def _exit_connector(self, *args) -> None:
        """Close the connection once the outermost block sharing it is done with it."""
        self._connection_depth -= 1

        if not self._connection_depth:
            self.connector.__exit__(*args)
