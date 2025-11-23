from odev.common.commands.odoobin import TEMPLATE_SUFFIX as ODOO_DB_TEMPLATE_SUFFIX
from odev.common.config import Config
from odev.common.connectors.git import GitConnector
from odev.common.databases import LocalDatabase
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevCommandTestCase
from tests.fixtures.matchers import OdoobinMatch


ODOO_DB_VERSION = "18.0"
"""Version to use in tests, keep in sync with branches pulled in GitHub workflows."""


class TestDatabaseCommands(OdevCommandTestCase):
    """Set up a test database for database-related command tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.__patch_odoobin_prep()
        cls.database_name = cls.run_name
        cls.template_name = cls.database_name + ODOO_DB_TEMPLATE_SUFFIX

    @classmethod
    def tearDownClass(cls):
        for database_name in (cls.database_name, cls.template_name):
            database = LocalDatabase(database_name)

            if database.exists:
                if database.venv.exists and not database.venv._global:
                    database.venv.remove()

                for worktree in database.worktrees:
                    worktree.connector.remove_worktree(worktree.path)

                database.drop()

        super().tearDownClass()

    @classmethod
    def __patch_odoobin_prep(cls):
        """Patch methods to allow the preparation of odoo-bin in the test environment."""
        cls.odev.config.paths.repositories = Config().paths.repositories
        cls._patch_object(GitConnector, [("_get_clone_options", ["--depth", "1", "--no-single-branch"])])
        cls._patch_object(OdoobinProcess, [], [("odoo_repositories", [GitConnector("odoo/odoo")])])
        cls._patch_object(LocalDatabase, [("pg_vector", True)])

    # --------------------------------------------------------------------------
    # Assertions
    # --------------------------------------------------------------------------

    def __assertDatabaseExist(self, name: str, exists: bool):  # noqa: N802
        """Assert that a database exists or not."""
        database = LocalDatabase(name)

        with database.psql(self.odev.name) as connector:
            connector.invalidate_cache(database.name)

            self.assertEqual(
                database.exists,
                exists,
                f"Database {name} {'does not exist' if exists else 'exists'}",
            )

            if database.exists:
                connector.revoke_database(database.name)

    def __assertDatabaseOdoo(self, name: str, is_odoo: bool):  # noqa: N802
        """Assert that a database is an Odoo database or not."""
        database = LocalDatabase(name)

        with database.psql(self.odev.name) as connector:
            connector.invalidate_cache(database.name)

            self.assertEqual(
                database.is_odoo,
                is_odoo,
                f"Database {name} is {'not ' if not is_odoo else ''}an Odoo database",
            )

            if database.exists:
                connector.revoke_database(database.name)

    def __assertDatabaseVersion(self, name: str, version: str):  # noqa: N802
        """Assert that a database has a specific Odoo version."""
        database = LocalDatabase(name)

        with database.psql(self.odev.name) as connector:
            connector.invalidate_cache(database.name)

            self.assertEqual(
                str(database.version),
                version,
                f"Database {name} has version {database.version}, expected {version}",
            )

            if database.exists:
                connector.revoke_database(database.name)

    def assertDatabaseExist(self, name: str):  # noqa: N802
        """Assert that a database exists."""
        self.__assertDatabaseExist(name, exists=True)

    def assertDatabaseNotExist(self, name: str):  # noqa: N802
        """Assert that a database does not exist."""
        self.__assertDatabaseExist(name, exists=False)

    def assertDatabaseIsOdoo(self, name: str):  # noqa: N802
        """Assert that a database is an Odoo database."""
        self.__assertDatabaseOdoo(name, is_odoo=True)

    def assertDatabaseIsNotOdoo(self, name: str):  # noqa: N802
        """Assert that a database is not an Odoo database."""
        self.__assertDatabaseOdoo(name, is_odoo=False)

    def assertDatabaseVersionEqual(self, name: str, version: str):  # noqa: N802
        """Assert that a database has a specific Odoo version."""
        self.__assertDatabaseVersion(name, version)

    def assertCalledWithOdoobin(  # noqa: N802
        self,
        stream_mock,
        database_name: str,
        args: list[str] | None = None,
        subcommand: str | None = None,
    ):
        """Assert that a mock was called with the expected odoo-bin command.

        :param stream_mock: The mock to assert.
        :param database_name: The name of the database.
        :param args: Additional arguments passed to odoo-bin.
        :param subcommand: The subcommand passed to odoo-bin.
        """
        stream_mock.assert_called_with(OdoobinMatch(database_name, args, subcommand))

    # --------------------------------------------------------------------------
    # Test cases
    # --------------------------------------------------------------------------

    def test_01_create_bare(self):
        """Command `odev create --bare` should create a new database but should not initialize it with Odoo."""
        self.assertDatabaseNotExist(self.database_name)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", "--bare", self.database_name)
            stream.assert_not_called()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsNotOdoo(self.database_name)

    def test_02_create_odoo(self):
        """Command `odev create` should create a new database and initialize it with Odoo."""
        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "create",
                "--version",
                ODOO_DB_VERSION,
                self.database_name,
                "--without-demo",
                "all",
            )
            self.assertCalledWithOdoobin(
                stream,
                self.database_name,
                ["--without-demo", "all", "--init", "base", "--stop-after-init"],
            )

        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database", stdout)
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_03_create_new_template(self):
        """Command `odev create` should create a new template database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertDatabaseNotExist(self.template_name)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", "--create-template", self.database_name)
            stream.assert_not_called()

        self.assertDatabaseExist(self.template_name)
        self.assertDatabaseIsOdoo(self.template_name)
        self.assertDatabaseVersionEqual(self.template_name, ODOO_DB_VERSION)

    def test_04_create_from_template(self):
        """Command `odev create` should create a new database from an existing template."""
        self.assertDatabaseExist(self.template_name)
        self.assertDatabaseIsOdoo(self.template_name)
        self.assertDatabaseVersionEqual(self.template_name, ODOO_DB_VERSION)

        if (database := LocalDatabase(self.database_name)).exists:
            database.drop()

        self.assertDatabaseNotExist(self.database_name)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command(
                "create",
                "--from-template",
                self.template_name,
                self.database_name,
            )
            stream.assert_not_called()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_05_create_from_template_no_value(self):
        """Command `odev create` should create a new database from an existing template, taking the current database name
        if no value given.
        """
        self.assertDatabaseExist(self.template_name)
        self.assertDatabaseIsOdoo(self.template_name)
        self.assertDatabaseVersionEqual(self.template_name, ODOO_DB_VERSION)

        if (database := LocalDatabase(self.database_name)).exists:
            database.drop()

        self.assertDatabaseNotExist(self.database_name)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", "--from-template", "", self.database_name)
            stream.assert_not_called()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_06_run(self):
        """Command `odev run` should run Odoo in a database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("run", self.database_name, "--stop-after-init")
            self.assertCalledWithOdoobin(stream, self.database_name, ["--stop-after-init"])

        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'", stdout)

    def test_07_run_from_template(self):
        """Command `odev run` should run Odoo in a database from a template, overriding the database if it exists."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseExist(self.template_name)
        self.assertDatabaseIsOdoo(self.template_name)
        self.assertDatabaseVersionEqual(self.template_name, ODOO_DB_VERSION)

        # Create a table in the database to ensure it is overridden
        database = LocalDatabase(self.database_name)
        database.query("CREATE TABLE test_table (id SERIAL PRIMARY KEY);")
        self.assertTrue(database.table_exists("test_table"))

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "run",
                "--from-template",
                self.template_name,
                self.database_name,
                "--stop-after-init",
            )
            self.assertCalledWithOdoobin(stream, self.database_name, ["--stop-after-init"])

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'", stdout)

        # The table should have been dropped when the database was overridden
        self.assertFalse(database.table_exists("test_table"))

    def test_08_run_from_template_no_value(self):
        """Command `odev run` should run Odoo in a database from a template, taking the current database name
        if no value given, overriding the database if it exists.
        """
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseExist(self.template_name)
        self.assertDatabaseIsOdoo(self.template_name)
        self.assertDatabaseVersionEqual(self.template_name, ODOO_DB_VERSION)

        # Create a table in the database to ensure it is overridden
        database = LocalDatabase(self.database_name)
        database.query("CREATE TABLE test_table (id SERIAL PRIMARY KEY);")
        self.assertTrue(database.table_exists("test_table"))

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("run", "--from-template", "", self.database_name, "--stop-after-init")
            self.assertCalledWithOdoobin(stream, self.database_name, ["--stop-after-init"])

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'", stdout)

        # The table should have been dropped when the database was overridden
        self.assertFalse(database.table_exists("test_table"))

    def test_09_run_from_invalid_template(self):
        """Command `odev run` should not delete the existing database if the template does not exist."""
        invalid_name = f"invalid-{self.template_name}"
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseNotExist(invalid_name)

        # Create a table in the database to ensure it is not overridden
        database = LocalDatabase(self.database_name)
        database.query("CREATE TABLE test_table (id SERIAL PRIMARY KEY);")
        self.assertTrue(database.table_exists("test_table"))

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "run",
                "--from-template",
                invalid_name,
                self.database_name,
                "--stop-after-init",
            )
            stream.assert_not_called()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertIn(f"Template database '{invalid_name}' does not exist", stdout)

        # The table should still exist as the database was not overridden
        self.assertTrue(database.table_exists("test_table"))

    def test_10_run_tests(self):
        """Command `odev test` should run tests on a database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("test", "--tags", ":TestSafeEval.test_expr", self.database_name)
            self.assertCalledWithOdoobin(
                stream,
                self.database_name,
                ["--stop-after-init", "--test-enable", "--test-tags", ":TestSafeEval.test_expr", "--init", "base"],
            )

        self.assertRegex(stdout, rf"Created database '{self.database_name}-[a-z0-9]{{8}}'")
        self.assertRegex(stdout, rf"Dropped database '{self.database_name}-[a-z0-9]{{8}}'")
        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}-", stdout)
        self.assertIn("No failing tests", stdout)

    def test_11_cloc(self):
        """Command `odev cloc` should print line of codes count for modules installed in a database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        stdout, _ = self.dispatch_command("cloc", self.database_name)
        self.assertIn(
            f"Running 'odoo-bin cloc' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'",
            stdout,
        )

    def test_12_run_with_addons_path(self):
        """Command `odev run` should run Odoo in a database, recursively detect additional addons paths
        and store the value of the repository for future usage.
        """
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        database = LocalDatabase(self.database_name)
        self.assertIsNone(database.repository)

        addon = "test/test-addons"
        addons_path_end = f"repositories/{addon}"
        addons_path = self.res_path / addons_path_end

        with (
            self.patch("odev.common.commands.odoobin.OdoobinCommand", "_guess_addons_paths", [addons_path]),
            self.patch_property(
                OdoobinProcess,
                "additional_repositories",
                (r for r in [GitConnector(addon)]),
            ),
        ):
            stdout, _ = self.dispatch_command("run", self.database_name, "--stop-after-init")

        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'", stdout)
        self.assertRegex(stdout, rf"--addons-path [^\s]+?{addons_path_end},[^\s]+?{addons_path_end}/submodule")
        self.assertEqual(database.repository.full_name, addon)

    def test_13_run_with_version(self):
        """Command `odev run` should run Odoo in a database with a specific version."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        version = "17.0"

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("run", "--version", version, self.database_name, "--stop-after-init")
            self.assertCalledWithOdoobin(stream, self.database_name, ["--stop-after-init"])

        self.assertIn(f"Running 'odoo-bin' in version '{version}' on database '{self.database_name}'", stdout)
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    # --------------------------------------------------------------------------
    # Test cases - delete
    # Keep at the end to avoid interference with other tests and to cleanup
    # databases as we go.
    # --------------------------------------------------------------------------

    def test_97_delete(self):
        """Command `odev delete` should delete a database if a name is provided."""
        self.assertDatabaseExist(self.template_name)
        stdout, _ = self.dispatch_command("delete", self.template_name)
        self.assertDatabaseNotExist(self.template_name)
        self.assertIn(f"Dropped database '{self.template_name}'", stdout)

    def test_98_delete_non_existent(self):
        """Command `odev delete` should display an error message when trying to delete a non-existent database."""
        inexistent_name = "non-existent-db"
        self.assertDatabaseNotExist(inexistent_name)
        _, stderr = self.dispatch_command("delete", inexistent_name)
        self.assertIn(f"No non-whitelisted database found named '{inexistent_name}'", stderr)

    def test_99_delete_expression(self):
        """Command `odev delete` should delete databases matching a regular expression."""
        self.assertDatabaseExist(self.database_name)

        with self.patch(self.odev.console, "confirm", return_value=True):
            stdout, _ = self.dispatch_command("delete", "--expression", "^odev-test-[a-z0-9]{8}")

        self.assertDatabaseNotExist(self.database_name)
        self.assertDatabaseNotExist(self.template_name)
        self.assertIn("You are about to delete the following databases:", stdout)
        self.assertRegex(stdout, r"Deleted \d+ databases")
