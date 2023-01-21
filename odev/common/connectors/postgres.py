"""PostgreSQL connector."""

from typing import ClassVar, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from odev.common.connectors import Connector


DEFAULT_DATABASE = "template1"


class PostgresConnector(Connector):
    """Connector class to interact with PostgreSQL."""

    _fallback_database: ClassVar[str] = DEFAULT_DATABASE
    """The database to connect to if none is specified."""

    _connection: Optional[psycopg2.extensions.connection] = None
    """The instance of a connection to the database engine."""

    cr: Optional[psycopg2.extensions.cursor] = None
    """The cursor to the database engine."""

    def __init__(self, database: Optional[str] = None):
        """Initialize the connector."""
        self.database = database or self._fallback_database

    def connect(self):
        """Connect to the database engine."""
        self._connection = psycopg2.connect(database=self.database)
        self._connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        self.cr = self._connection.cursor()

    def disconnect(self):
        """Disconnect from the database engine."""
        if self.cr:
            self.cr.close()
        if self._connection:
            self._connection.commit()
            self._connection.close()
            del self._connection
