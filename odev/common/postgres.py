"""PostgreSQL database class."""

from abc import ABC
from contextlib import nullcontext
from typing import Mapping, MutableMapping, Optional

from psycopg2.errors import InvalidTableDefinition

from odev.common.connectors import PostgresConnector
from odev.common.logging import logging
from odev.common.mixins import PostgresConnectorMixin, ensure_connected


__all__ = ["PostgresDatabase"]


logger = logging.getLogger(__name__)


class PostgresDatabase(PostgresConnectorMixin):
    """Class for manipulating PostgreSQL (local) databases."""

    connector: PostgresConnector
    """Instance of the connector to the database engine."""

    tables: MutableMapping[str, "PostgresTable"] = {}
    """Mapping of tables in the database."""

    def __init__(self, name: str):
        """Initialize the database."""
        super().__init__()

        self.name: str = name
        """The name of the database."""

        self.prepare_database()

    def __enter__(self):
        self.connector = self._connector_class(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self._connector_class(self.name).__exit__(*args)

    def __repr__(self):
        """Return the representation of the database."""
        return f"{self.__class__.__name__}({self.name!r})"

    def __str__(self):
        """Return the string representation of the database."""
        return self.name

    def prepare_database(self):
        """Prepare the database and ensure it exists in PostgreSQL."""
        with self.psql().nocache():
            if not self.exists():
                logger.debug(f"Creating database {self.name!r}")
                self.create()

    def size(self) -> int:
        with self.psql() as psql:
            result = psql.query(
                f"""
                SELECT pg_database_size('{self.name}')
                LIMIT 1
                """
            )
        return isinstance(result, list) and result[0][0] or 0

    def exists(self) -> bool:
        """Check if the database exists."""
        with self.psql() as psql:
            return bool(psql.database_exists(self.name))

    def create(self, template: Optional[str] = None) -> bool:
        """Create the database.

        :param template: The name of the template to copy.
        """
        with self.psql() as psql:
            return psql.create_database(self.name, template=template)

    def drop(self) -> bool:
        """Drop the database."""
        self.connector.disconnect()
        with self.psql() as psql:
            return psql.drop_database(self.name)

    @ensure_connected
    def table_exists(self, table: str) -> bool:
        """Check if a table exists in the database."""
        return self.connector.table_exists(table)

    @ensure_connected
    def create_table(self, table: str, columns: Mapping[str, str]):
        """Create a table in the database."""
        return self.connector.create_table(table, columns)

    @ensure_connected
    def column_exists(self, table: str, column: str) -> list[str]:
        """Check if a column exist in a table."""
        return self.columns_exist(table, [column])

    @ensure_connected
    def columns_exist(self, table: str, columns: list[str]) -> list[str]:
        """Check if columns exist in a table."""
        return self.connector.columns_exist(table, columns)

    @ensure_connected
    def create_column(self, table: str, column: str, definition: str):
        """Create a column in table."""
        return self.connector.create_column(table, column, definition)

    @ensure_connected
    def query(self, query: str, nocache: bool = False):
        """Execute a query on the database."""
        with self.connector.nocache() if nocache else nullcontext():
            return self.connector.query(query)

    @ensure_connected
    def constraint(self, table: str, name: str, definition: str):
        """Create a constraint in the database."""
        return self.connector.query(
            f"""
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE {table}
                    ADD CONSTRAINT {name}
                    {definition};
                EXCEPTION
                    WHEN duplicate_table THEN
                    WHEN duplicate_object THEN
                        NULL;
                END;
            END $$;
            """
        )


class PostgresTable(ABC):
    """Representation of a PostgreSQL table in a database."""

    _columns: Optional[Mapping[str, str]] = None
    """Columns definition of the table, must be set in subclass.
    Format: `{column_name: column_type}` where `column_type` is the SQL definition of the column.
    """

    _constraints: Optional[Mapping[str, str]] = None
    """Constraints definition of the table, must be set in subclass.
    Format: `{constraint_name: constraint_definition}` where `constraint_definition`.
    """

    def __init__(self, database: PostgresDatabase, name: Optional[str] = None):
        """Initialize the database."""

        self.database: PostgresDatabase = database
        """The database in which the table is."""

        self.name: str = name or self.name
        """Name of the table in which data is stored, must be set in subclass."""

        with self.database:
            self.prepare_database_table()

        self.database.tables[self.name] = self

    def prepare_database_table(self):
        """Prepare the table and ensures it has the correct definition and constraints applied."""
        if self._columns is not None:
            if not self.database.table_exists(self.name):
                logger.debug(f"Creating table {self.name!r} in database {self.database!r}")
                self.database.create_table(self.name, self._columns)
            else:
                if missing_columns := self.database.columns_exist(self.name, list(self._columns.keys())):
                    for column in missing_columns:
                        self.__add_missing_column(column)

        if self._constraints is not None:
            for name, definition in self._constraints.items():
                logger.debug(f"Creating constraint {name!r} on table {self.name!r} in database {self.database.name!r}")
                self.database.constraint(self.name, name, definition)

    def clear(self):
        """Clear the table."""
        self.database.query(f"DELETE FROM {self.name}")

    def __add_missing_column(self, column: str):
        """Add a missing column to an existing table."""
        assert self._columns is not None
        logger.debug(f"Adding column {column!r} to table {self.name!r} in database {self.database.name!r}")

        try:
            self.database.create_column(self.name, column, self._columns[column])
        except RuntimeError as error:
            if isinstance(error.__cause__, InvalidTableDefinition):
                logger.debug(f"Error adding column {column!r} to table {self.name!r}: {error.__cause__}")

                # When changing the definition of an existing table and renaming the column containing the primary key,
                # we need to drop the existing constraint before proceeding with the creation of the new column.
                # Since, by design, the tables for the datastore are initialized before the upgrade scripts are run,
                # we need to handle this case here
                if "multiple primary keys for table" in str(error.__cause__):
                    self.database.query(f"ALTER TABLE {self.name} DROP CONSTRAINT IF EXISTS {self.name}_pkey")
                    self.database.create_column(self.name, column, self._columns[column])
            else:
                raise
