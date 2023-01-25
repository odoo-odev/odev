"""PostgreSQL connector."""

import textwrap
from functools import lru_cache
from typing import (
    ClassVar,
    List,
    Optional,
    Sequence,
    Union,
)

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from odev.common.connectors import Connector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DEFAULT_DATABASE = "postgres"


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
        logger.debug(f"Connected to database {self.database!r}")

    def disconnect(self):
        """Disconnect from the database engine."""
        if self.cr:
            self.cr.close()
            del self.cr
        if self._connection:
            self._connection.commit()
            self._connection.close()
            del self._connection
        logger.debug(f"Disconnected from database {self.database!r}")

    @lru_cache
    def query(
        self, query: Union[str, sql.SQL], params: Optional[Sequence] = None
    ) -> Union[Optional[List[tuple]], bool]:
        """Execute a query and return its result.

        :param query: The query to execute.
        :param params: Additional parameters to pass to the cursor.
        """
        assert self.cr, "The cursor is not initialized, connect first."

        if isinstance(query, sql.SQL):
            query = query.as_string(self.cr)

        if isinstance(query, str):
            query = textwrap.dedent(query).strip()
            query_lower = query.lower()

        logger.debug(f"Executing PostgreSQL query against database {self.database!r}':\n{query}")
        self.cr.execute(query, params)
        return self.cr.fetchall() if query_lower.startswith("select") or " returning " in query_lower else True
