from unittest.mock import MagicMock

from psycopg2.errors import InvalidTableDefinition

from odev.common.connectors import PostgresConnector
from odev.common.postgres import PostgresDatabase, PostgresTable

from tests.fixtures import OdevTestCase


class TestPostgresColumnsExist(OdevTestCase):
    """`columns_exist` reports the columns missing from a table, it does not need a live database."""

    def columns_exist(self, existing: list[str], requested: list[str]) -> list[str]:
        """Run `columns_exist` against a connector whose query returns the given existing columns."""
        connector = PostgresConnector.__new__(PostgresConnector)
        connector.query = lambda _: [(column,) for column in existing]  # type: ignore [method-assign]
        return connector.columns_exist("table", requested)

    def test_01_some_columns_missing(self):
        """Only the requested columns absent from the table should be returned."""
        self.assertEqual(self.columns_exist(["id"], ["id", "name", "date"]), ["name", "date"])

    def test_02_no_column_exists(self):
        """An empty result means none of the requested columns exist, so all of them are missing.

        A table created from an older definition holds none of the new columns; reporting nothing missing
        would leave it unmigrated.
        """
        self.assertEqual(self.columns_exist([], ["id", "name"]), ["id", "name"])

    def test_03_all_columns_exist(self):
        """A table holding every requested column should report nothing missing."""
        self.assertEqual(self.columns_exist(["id", "name"], ["id", "name"]), [])

    def test_04_order_is_preserved(self):
        """Missing columns should be reported in the order they were requested."""
        self.assertEqual(self.columns_exist(["b"], ["a", "b", "c"]), ["a", "c"])

    def test_05_no_column_requested(self):
        """Asking for no column should report nothing missing without querying the database."""
        connector = PostgresConnector.__new__(PostgresConnector)

        def fail_on_query(_):
            raise AssertionError("no query should be issued when no column is requested")

        connector.query = fail_on_query  # type: ignore [method-assign]
        self.assertEqual(connector.columns_exist("table", []), [])

    def test_06_columns_must_be_a_list(self):
        """Passing a bare string would build a query over its characters and is rejected."""
        connector = PostgresConnector.__new__(PostgresConnector)

        with self.assertRaises(TypeError):
            connector.columns_exist("table", "id")  # type: ignore [arg-type]


class TestPostgresTable(OdevTestCase):
    """Tables should be brought in line with the definition declared on their subclass."""

    table_name = "odev_test_table"

    def setUp(self):
        super().setUp()
        self.database = MagicMock(spec=PostgresDatabase)
        """The database the tables are built against, kept aside to assert the queries it received."""

        self.database.name = "odev-test"
        self.database.tables = {}
        self.database.columns_exist.return_value = []

    def build_table(
        self,
        columns: dict[str, str] | None,
        constraints: dict[str, str] | None = None,
        missing: list[str] | None = None,
    ) -> PostgresTable:
        """Build a table against the mocked database, reporting the given columns as missing.

        :param columns: The columns declared on the table subclass.
        :param constraints: The constraints declared on the table subclass.
        :param missing: The columns `columns_exist` should report as absent from the table.
        """
        self.database.columns_exist.return_value = missing or []
        table_name = self.table_name

        class TestTable(PostgresTable):
            name = table_name
            _columns = columns
            _constraints = constraints

        return TestTable(self.database)

    def test_01_registers_itself_on_the_database(self):
        """A table should be reachable from the database it was built against."""
        table = self.build_table({"id": "SERIAL PRIMARY KEY"})

        self.assertIs(self.database.tables[self.table_name], table)

    def test_02_prepare_creates_the_table(self):
        """Preparing a table should create it from the columns of its definition."""
        columns = {"id": "SERIAL PRIMARY KEY", "name": "VARCHAR"}
        self.build_table(columns).prepare_database_table()

        self.database.create_table.assert_called_once_with(self.table_name, columns)

    def test_03_prepare_without_columns_does_nothing(self):
        """A table whose subclass declares no column has nothing to create."""
        self.build_table(None).prepare_database_table()

        self.database.create_table.assert_not_called()
        self.database.columns_exist.assert_not_called()

    def test_04_prepare_adds_missing_columns(self):
        """Columns absent from an existing table should be added to it.

        `CREATE TABLE IF NOT EXISTS` leaves an existing table alone, so a column added to the definition
        can only reach the table through this pass.
        """
        table = self.build_table({"id": "SERIAL PRIMARY KEY", "comment": "VARCHAR"}, missing=["comment"])
        table.prepare_database_table()

        self.database.create_column.assert_called_once_with(self.table_name, "comment", "VARCHAR")

    def test_05_prepare_without_missing_columns(self):
        """A table already matching its definition should not be altered."""
        self.build_table({"id": "SERIAL PRIMARY KEY"}).prepare_database_table()

        self.database.create_column.assert_not_called()

    def test_06_prepare_applies_constraints(self):
        """Constraints declared on the table should be applied when it is prepared."""
        table = self.build_table(
            {"id": "SERIAL PRIMARY KEY", "name": "VARCHAR"},
            {"name_unique": "UNIQUE (name)"},
        )
        table.prepare_database_table()

        self.database.constraint.assert_called_once_with(self.table_name, "name_unique", "UNIQUE (name)")

    def test_07_constraints_need_columns(self):
        """Constraints are applied from within the columns pass and are skipped without a definition."""
        self.build_table(None, {"name_unique": "UNIQUE (name)"}).prepare_database_table()

        self.database.constraint.assert_not_called()

    def test_08_clear_empties_the_table(self):
        """Clearing a table should delete its rows, not the table itself."""
        self.build_table({"id": "SERIAL PRIMARY KEY"}).clear()

        self.database.query.assert_called_once_with(f"DELETE FROM {self.table_name}")


class TestPostgresTableMissingColumnErrors(OdevTestCase):
    """Renaming a primary key column requires dropping the constraint left by the previous definition."""

    table_name = "odev_test_table"

    def setUp(self):
        super().setUp()
        self.database = MagicMock(spec=PostgresDatabase)
        """The database the table is built against, kept aside to assert the queries it received."""

        self.database.name = "odev-test"
        self.database.tables = {}
        self.database.columns_exist.return_value = ["identifier"]

    def build_table(self, error: Exception) -> PostgresTable:
        """Build a table whose first `create_column` call raises the given error."""
        self.database.create_column.side_effect = [error, None]
        table_name = self.table_name

        class TestTable(PostgresTable):
            name = table_name
            _columns = {"identifier": "SERIAL PRIMARY KEY"}

        return TestTable(self.database)

    def runtime_error(self, cause: Exception) -> RuntimeError:
        """Build the error raised by the connector thread when a query fails."""
        error = RuntimeError(f"Exception in thread: {cause}")
        error.__cause__ = cause

        return error

    def test_01_drops_the_stale_primary_key(self):
        """A leftover primary key should be dropped so the renamed column can be created."""
        cause = InvalidTableDefinition('multiple primary keys for table "odev_test_table" are not allowed')

        self.build_table(self.runtime_error(cause)).prepare_database_table()

        self.database.query.assert_called_once_with(
            f"ALTER TABLE {self.table_name} DROP CONSTRAINT IF EXISTS {self.table_name}_pkey"
        )
        self.assertEqual(self.database.create_column.call_count, 2)

    def test_02_other_table_definition_errors_are_swallowed(self):
        """Another invalid definition should be logged without retrying nor dropping a constraint."""
        cause = InvalidTableDefinition("column is of type integer but default expression is of type text")

        self.build_table(self.runtime_error(cause)).prepare_database_table()

        self.database.query.assert_not_called()
        self.assertEqual(self.database.create_column.call_count, 1)

    def test_03_unrelated_runtime_errors_are_raised(self):
        """A failure unrelated to the table definition should surface to the caller."""
        table = self.build_table(self.runtime_error(ValueError("boom")))

        with self.assertRaises(RuntimeError):
            table.prepare_database_table()


class TestPostgresDatabaseTables(OdevTestCase):
    """Each database should own the mapping of the tables registered against it."""

    def test_01_tables_are_not_shared_between_databases(self):
        """Registering a table on one database should not make it visible on another.

        The mapping used to be a class attribute, so every database instance shared a single registry and
        tables collided across databases on their name alone.
        """
        first = PostgresDatabase.__new__(PostgresDatabase)
        first.tables = {}
        second = PostgresDatabase.__new__(PostgresDatabase)
        second.tables = {}

        first.tables["history"] = MagicMock(spec=PostgresTable)

        self.assertEqual(second.tables, {})
        self.assertIsNot(first.tables, second.tables)

    def test_02_tables_are_instance_attributes(self):
        """The registry should not live on the class, where every database would share it."""
        self.assertNotIn("tables", PostgresDatabase.__dict__)
        self.assertIn("tables", vars(self.odev.store))

    def test_03_datastore_registers_its_tables(self):
        """The odev datastore should hold the three tables it is made of."""
        self.assertEqual(set(self.odev.store.tables), {"databases", "history", "secrets"})
