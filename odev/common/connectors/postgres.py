"""PostgreSQL connector."""

import textwrap
from typing import (
    ClassVar,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import psycopg2
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

    _query_cache: ClassVar[MutableMapping[Tuple[str, str], List[tuple]]] = {}
    """Simple cache of queries."""

    cr: Optional[psycopg2.extensions.cursor] = None
    """The cursor to the database engine."""

    def __init__(self, database: Optional[str] = None):
        """Initialize the connector."""
        self.database: str = database or self._fallback_database
        """The name of the database to connect to."""

    def connect(self):
        """Connect to the database engine."""
        if self._connection is None:
            self._connection = psycopg2.connect(database=self.database)
            self._connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        if self.cr is None:
            self.cr = self._connection.cursor()

    def disconnect(self):
        """Disconnect from the database engine."""
        if self.cr:
            self.cr.close()
            del self.cr

        if self._connection:
            self._connection.commit()
            self._connection.close()
            del self._connection

    def query(
        self, query: str, params: Optional[Sequence] = None, nocache: bool = False
    ) -> Union[Optional[List[tuple]], bool]:
        """Execute a query and return its result.

        :param query: The query to execute.
        :param params: Additional parameters to pass to the cursor.
        :param nocache: Whether to bypass the cache. Select statements are cached by default.
        """
        assert self.cr, "The cursor is not initialized, connect first"
        query = textwrap.dedent(query).strip()
        query_lower = query.lower()
        is_select = query_lower.startswith("select")
        expect_result = is_select or " returning " in query_lower

        if not nocache and is_select and (self.database, query) in self._query_cache:
            return self._query_cache[(self.database, query)]

        logger.debug(f"Executing PostgreSQL query against database {self.database!r}:\n{query}")
        self.cr.execute(query, params)

        if not expect_result:
            return True

        result = self.cr.fetchall()

        if not nocache and is_select and result:
            self._query_cache[(self.database, query)] = result

        return result

    def create_database(self, database: str) -> bool:
        """Create a database.

        :param database: The name of the database to create.
        :return: Whether the database was created.
        :rtype: bool
        """
        return bool(self.query(f"CREATE DATABASE {database}"))

    def drop_database(self, database: str) -> bool:
        """Drop a database.

        :param database: The name of the database to drop.
        :return: Whether the database was dropped.
        :rtype: bool
        """
        return bool(self.query(f"DROP DATABASE IF EXISTS {database}"))

    def database_exists(self, database: str) -> bool:
        """Check whether a database exists.

        :param database: The name of the database to check.
        :return: Whether the database exists.
        :rtype: bool
        """
        return bool(
            self.query(
                f"""
                SELECT 1
                FROM pg_database
                WHERE datname = '{database}'
                """
            )
        )

    def table_exists(self, table: str) -> bool:
        """Check whether a table exists in the current database.

        :param table: The name of the table to check.
        :return: Whether the table exists.
        :rtype: bool
        """
        return bool(
            self.query(
                f"""
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{table}'
                    AND c.relkind IN ('r', 'v', 'm')
                    AND n.nspname = current_schema
                """
            )
        )

    def create_table(self, table: str, columns: Mapping[str, str]) -> bool:
        """Create a table in the current database.

        :param table: The name of the table to create.
        :param columns: The columns to create.
        :return: Whether the table was created.
        :rtype: bool
        """
        sql_columns: str = ", ".join(f"{name} {attributes}" for name, attributes in columns.items())
        return bool(self.query(f"CREATE TABLE IF NOT EXISTS {table} ({sql_columns})"))
