"""PostgreSQL connector."""

import textwrap
from contextlib import contextmanager, nullcontext
from typing import (
    ClassVar,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, QueryCanceledError, cursor as PsycopgCursor

from odev.common import string
from odev.common.connectors import Connector
from odev.common.console import console
from odev.common.logging import DEBUG_SQL, LOG_LEVEL, logging
from odev.common.signal_handling import capture_signals
from odev.common.thread import Thread


logger = logging.getLogger(__name__)


DEFAULT_DATABASE = "postgres"


class Cursor(PsycopgCursor):
    """Extended Psycopg cursor class to add some convenience methods."""

    @contextmanager
    def transaction(self):
        """Enter a new transaction and either commit or rollback on exit based on the result
        of operations.
        """
        self.execute("BEGIN")

        try:
            yield
        except Exception as e:
            self.execute("ROLLBACK")
            raise e
        finally:
            self.execute("COMMIT")


class PostgresConnector(Connector):
    """Connector class to interact with PostgreSQL."""

    _fallback_database: ClassVar[str] = DEFAULT_DATABASE
    """The database to connect to if none is specified."""

    _connection: Optional[psycopg2.extensions.connection] = None
    """The instance of a connection to the database engine."""

    _query_cache: ClassVar[MutableMapping[Tuple[str, str], Union[List[tuple], Literal[False]]]] = {}
    """Simple cache of queries."""

    cr: Optional[Cursor] = None
    """The cursor to the database engine."""

    _nocache: bool = False
    """Whether to disable caching of SQL queries."""

    def __init__(self, database: Optional[str] = None):
        """Initialize the connector."""
        super().__init__()

        self.database: str = database or self._fallback_database
        """The name of the database to connect to."""

    @property
    def url(self) -> str:
        """Return the URL of the database."""
        return f"postgresql://localhost/{self.database}"

    def connect(self):
        """Connect to the database engine."""
        if self._connection is None:
            self._connection = psycopg2.connect(database=self.database)  # type: ignore [assignment]
            self._connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        if self.cr is None:
            self.cr = Cursor(self._connection)

    def disconnect(self):
        """Disconnect from the database engine."""
        if self.cr is not None:
            self.cr.close()
            del self.cr

        if self._connection is not None:
            self._connection.commit()
            self._connection.close()
            del self._connection

    def invalidate_cache(self, database: Optional[str] = None):
        """Invalidate the cache for a given database."""
        database = database or self.database
        logger.debug(f"Invalidating SQL cache for database {database!r}")
        PostgresConnector._query_cache = {
            key: value for key, value in self.__class__._query_cache.items() if key[0] != database
        }

    @contextmanager
    def nocache(self):
        """Context manager to disable caching of SQL queries."""
        self.__class__._nocache = True
        yield
        self.__class__._nocache = False

    def query(
        self,
        query: str,
        params: Optional[Sequence] = None,
        transaction: bool = True,
    ) -> Union[Optional[List[tuple]], bool]:
        """Execute a query and return its result.

        :param query: The query to execute.
        :param params: Additional parameters to pass to the cursor.
        :param transaction: Whether to execute the query in a transaction.
        """
        assert self.cr is not None, "The cursor is not initialized, connect first"
        query = textwrap.dedent(query).strip()
        query_lower = query.lower()
        is_select = query_lower.startswith("select")
        expect_result = is_select or " returning " in query_lower

        if is_select and not self.__class__._nocache and (self.database, query) in self.__class__._query_cache:
            result = self.__class__._query_cache[(self.database, query)]
            if DEBUG_SQL:
                logger.debug(f"Returning cached PostgreSQL result for query against database {self.database!r}:")
                console.code(string.indent(query, 4), "postgresql")
                console.print(f"[color.black]{string.indent('─' * 80, 4)}[/color.black]")
                console.code(string.indent(str(result), 4), "python")
            return result

        def signal_handler_cancel_statement(*args, **kwargs):
            """Cancel the SQL query currently running."""
            logger.warning("Aborting execution of SQL query")
            logger.debug(f"Aborting query:\n{query}")

            if self.cr is not None:
                self.cr.connection.cancel()

        with (
            self.cr.transaction() if transaction else nullcontext(),
            capture_signals(handler=signal_handler_cancel_statement),
        ):
            if LOG_LEVEL == "DEBUG" and DEBUG_SQL:
                logger.debug(f"Executing PostgreSQL query against database {self.database!r}:")
                console.code(string.indent(query, 4), "postgresql")

            thread = Thread(target=self.cr.execute, args=(query, params))

            try:
                thread.start()
                thread.join()
            except RuntimeError as error:
                if isinstance(error.__cause__, QueryCanceledError):
                    return False
                raise error

            result = expect_result and self.cr.fetchall()

        if is_select and not self.__class__._nocache:
            if DEBUG_SQL:
                logger.debug(f"Caching PostgreSQL result for query against {self.database!r}:")
                console.code(string.indent(str(result), 4), "python")
            self.__class__._query_cache[(self.database, query)] = result

        return result if expect_result else True

    def create_database(self, database: str, template: Optional[str] = None) -> bool:
        """Create a database.

        :param database: The name of the database to create.
        :return: Whether the database was created.
        :rtype: bool
        """
        self.invalidate_cache(database="postgres")
        return bool(
            self.query(
                f"""
                CREATE DATABASE "{database}"
                    WITH TEMPLATE "{template or 'template0'}"
                    LC_COLLATE 'C'
                    ENCODING 'unicode'
                """,
                transaction=False,
            )
        )

    def drop_database(self, database: str) -> bool:
        """Drop a database.

        :param database: The name of the database to drop.
        :return: Whether the database was dropped.
        :rtype: bool
        """
        self.invalidate_cache(database="postgres")
        self.query(
            f"""
            REVOKE CONNECT ON DATABASE "{database}"
            FROM PUBLIC
            """
        )

        self.query(
            f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE
                -- don't kill my own connection!
                pid <> pg_backend_pid()
                -- don't kill the connections to other databases
                AND datname = '{database}'
            """
        )

        res = bool(
            self.query(
                f"""
                DROP DATABASE IF EXISTS "{database}"
                """,
                transaction=False,
            )
        )
        self.invalidate_cache(database=database)
        return res

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
            ),
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
                """,
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

    def columns_exist(self, table: str, columns: list[str]) -> list[str]:
        """Check whether a column exists in a table.
        :param table: The name of the table to check.
        :param columns: The name of the column to check.
        :return: Whether the column exists.
        :rtype: list[str]
        """
        if not isinstance(columns, list):
            raise TypeError("Columns should be a list of strings")

        results = self.query(
            f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name IN ({','.join([f"'{c}'" for c in columns])})
            """,
        )

        if results and isinstance(results, list) and columns:
            return [c for c in columns if c not in [r[0] for r in results]]
        else:
            return []

    def create_column(self, table: str, column: str, attributes: str) -> bool:
        """Create a column in a table.
        :param table: The name of the table to create the column in.
        :param column: The name of the column to create.
        :param attributes: The attributes of the column.
        :return: Whether the column was created.
        :rtype: bool
        """
        return bool(
            self.query(
                f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS {column} {attributes}
                """
            )
        )
