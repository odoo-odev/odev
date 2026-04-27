from typing import cast
from unittest.mock import PropertyMock, patch

from odev.common.commands.odoobin import TEMPLATE_SUFFIX as ODOO_DB_TEMPLATE_SUFFIX
from odev.common.connectors.git import GitConnector
from odev.common.databases import LocalDatabase, Repository
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevCommandTestCase
from tests.fixtures.odoobin_run_mock import (
    FAKE_ODOO_ROOT,
    assert_any_odoobin_invocation,
    assert_last_odoobin_invocation,
    ensure_fake_venvs,
    iter_odoobin_calls,
    start_run_script_recorder,
    stub_minimal_odoo_pg_metadata,
)


ODOO_DB_VERSION = "18.0"
"""Version to use in tests, keep in sync with branches pulled in GitHub workflows."""


class TestDatabaseCommands(OdevCommandTestCase):
    """Database-related command tests (PostgreSQL real; odoo-bin execution mocked)."""

    _odoobin_run_script_calls: list = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.__patch_odoobin_prep()
        ensure_fake_venvs()
        cls._odoobin_run_script_calls = []
        cls._patches.append(start_run_script_recorder(cls._odoobin_run_script_calls))

        def _noop(_self):
            return None

        for _name in ("prepare_odoobin", "update_worktrees"):
            pr = patch.object(OdoobinProcess, _name, _noop)
            cls._patches.append(pr)
            pr.start()

        prp = patch.object(OdoobinProcess, "odoo_path", new_callable=PropertyMock, return_value=FAKE_ODOO_ROOT)
        cls._patches.append(prp)
        prp.start()

        cls.database_name = cls.run_name
        cls.template_name = cls.database_name + ODOO_DB_TEMPLATE_SUFFIX

    def setUp(self):
        super().setUp()
        self._odoobin_run_script_calls.clear()

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
        repos = cls.run_path / "repositories"
        repos.mkdir(parents=True, exist_ok=True)
        cls.odev.config.paths.repositories = repos
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

    def assertNoOdoobinRun(self):  # noqa: N802
        self.assertFalse(list(iter_odoobin_calls(self._odoobin_run_script_calls)))

    # --------------------------------------------------------------------------
    # Test cases
    # --------------------------------------------------------------------------

    def test_01_create_bare(self):
        """Command `odev create --bare` should create a new database but should not initialize it with Odoo."""
        self.assertDatabaseNotExist(self.database_name)

        self.dispatch_command("create", "--bare", self.database_name)
        self.assertNoOdoobinRun()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsNotOdoo(self.database_name)

    def test_02_create_odoo(self):
        """Command `odev create` should create a new database and invoke odoo-bin with init arguments."""
        stdout, _ = self.dispatch_command(
            "create",
            "--version",
            ODOO_DB_VERSION,
            self.database_name,
            "--without-demo",
            "all",
        )
        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--without-demo", "all", "--init", "base", "--stop-after-init"],
        )

        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database", stdout)
        self.assertDatabaseExist(self.database_name)
        stub_minimal_odoo_pg_metadata(LocalDatabase(self.database_name), ODOO_DB_VERSION)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_03_create_new_template(self):
        """Command `odev create` should create a new template database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertDatabaseNotExist(self.template_name)

        self.dispatch_command("create", "--create-template", self.database_name)
        self.assertNoOdoobinRun()

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

        self.dispatch_command(
            "create",
            "--from-template",
            self.template_name,
            self.database_name,
        )
        self.assertNoOdoobinRun()

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

        self.dispatch_command("create", "--from-template", "", self.database_name)
        self.assertNoOdoobinRun()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_06_run(self):
        """Command `odev run` should invoke odoo-bin for a database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        stdout, _ = self.dispatch_command("run", self.database_name, "--stop-after-init")
        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--stop-after-init"],
        )

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

        stdout, _ = self.dispatch_command(
            "run",
            "--from-template",
            self.template_name,
            self.database_name,
            "--stop-after-init",
        )
        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--stop-after-init"],
        )

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

        stdout, _ = self.dispatch_command("run", "--from-template", "", self.database_name, "--stop-after-init")
        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--stop-after-init"],
        )

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

        stdout, _ = self.dispatch_command(
            "run",
            "--from-template",
            invalid_name,
            self.database_name,
            "--stop-after-init",
        )
        self.assertNoOdoobinRun()

        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)
        self.assertIn(f"Template database '{invalid_name}' does not exist", stdout)

        # The table should still exist as the database was not overridden
        self.assertTrue(database.table_exists("test_table"))

    def test_10_run_tests(self):
        """Command `odev test` should invoke odoo-bin with test arguments on a scratch database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        stdout, _ = self.dispatch_command("test", "--tags", ":TestSafeEval.test_expr", self.database_name)

        def _is_test_run(argv: list[str]) -> bool:
            return "--test-enable" in argv and any(":TestSafeEval.test_expr" in arg for arg in argv)

        assert_any_odoobin_invocation(self, self._odoobin_run_script_calls, predicate=_is_test_run)

        self.assertRegex(stdout, rf"Created database '{self.database_name}-[a-z0-9]{{8}}'")
        self.assertRegex(stdout, rf"Dropped database '{self.database_name}-[a-z0-9]{{8}}'")
        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}-", stdout)
        self.assertIn("No failing tests", stdout)

    def test_11_cloc(self):
        """Command `odev cloc` should invoke odoo-bin cloc for a database."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        stdout, _ = self.dispatch_command("cloc", self.database_name)
        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            subcommand="cloc",
        )
        self.assertIn(
            f"Running 'odoo-bin cloc' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'",
            stdout,
        )

    def test_12_run_with_addons_path(self):
        """Command `odev run` should pass detected addons paths and persist the repository on the database."""
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

        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--stop-after-init"],
        )
        _interp, _script, argv, _st, _inp = list(iter_odoobin_calls(self._odoobin_run_script_calls))[-1]
        joined = " ".join(argv)
        self.assertIn(addons_path_end, joined)
        self.assertGreaterEqual(joined.count(addons_path_end), 2)

        self.assertIn(f"Running 'odoo-bin' in version '{ODOO_DB_VERSION}' on database '{self.database_name}'", stdout)
        repository = cast(Repository, database.repository)
        self.assertEqual(repository.full_name, addon)

    def test_13_run_with_version(self):
        """Command `odev run` should invoke odoo-bin using the requested Odoo version."""
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

        version = "17.0"

        with self.patch(OdoobinProcess, "_get_python_version", return_value=None):
            stdout, _ = self.dispatch_command("run", "--version", version, self.database_name, "--stop-after-init")

        assert_last_odoobin_invocation(
            self,
            self._odoobin_run_script_calls,
            database_name=self.database_name,
            argv_contains=["--stop-after-init"],
        )

        self.assertIn(f"Running 'odoo-bin' in version '{version}' on database '{self.database_name}'", stdout)
        self.assertDatabaseExist(self.database_name)
        self.assertDatabaseIsOdoo(self.database_name)
        self.assertDatabaseVersionEqual(self.database_name, ODOO_DB_VERSION)

    def test_14_run_empty_db_warning(self):
        """Command `odev run` should warn the user when running on an empty database without a version."""
        empty_db = f"{self.database_name}-empty"
        LocalDatabase(empty_db).create()
        try:
            with (
                self.patch("odev.common.bash", "stream", return_value=iter([])),
                self.patch("odev.common.bash", "run", return_value=None),
            ):
                # odoo-bin would fail on an empty DB, but we've mocked bash to avoid the error
                stdout, stderr = self.dispatch_command("run", empty_db, "--stop-after-init")

            # Logging goes to stdout in these tests
            combined_output = stdout + stderr
            self.assertIn(f"Database {empty_db!r} is not an Odoo database. Defaulting to 'master'.", combined_output)
            self.assertIn(
                f"Consider using 'odev create -V <version> {empty_db}' to initialize it properly.", combined_output
            )
        finally:
            LocalDatabase(empty_db).drop()

    def test_15_test_non_existent_db(self):
        """Command `odev test` should work even if the target database does not exist, provided a version is given."""
        non_existent_db = f"{self.database_name}-non-existent"
        self.assertDatabaseNotExist(non_existent_db)

        # Mock run_command to avoid actually running 'create' or 'test'
        with (
            self.patch("odev.common.bash", "stream", return_value=iter([])),
            self.patch("odev.common.odev.Odev", "run_command"),
        ):
            # This should not raise SystemExit or any exception
            self.dispatch_command("test", "-V", ODOO_DB_VERSION, "--tags", ":base", non_existent_db)

    def test_16_info(self):
        """Command `odev info` should print details about a local Odoo database."""
        stdout, _ = self.dispatch_command("info", self.database_name)
        self.assertIn("Database Information", stdout)
        self.assertIn("Local Process", stdout)

    def test_17_neutralize(self):
        """Command `odev neutralize` should neutralize the target database."""
        with self.patch(LocalDatabase, "neutralize") as neutralize:
            stdout, _ = self.dispatch_command("neutralize", self.database_name)

        neutralize.assert_called_once_with()
        self.assertIn("has been neutralized", stdout)

    def test_18_dump(self):
        """Command `odev dump` should report where the dump was saved."""
        dump_file = self.run_path / f"{self.database_name}.zip"
        with self.patch(LocalDatabase, "dump", return_value=dump_file):
            stdout, _ = self.dispatch_command("dump", self.database_name, "--filestore")

        self.assertIn(f"dumped to {dump_file}", stdout)

    # --------------------------------------------------------------------------
    # Test cases - additional database commands (error / guard paths)
    # --------------------------------------------------------------------------

    def test_90_restore_invalid_dump_file(self):
        """`odev restore` should reject a missing backup path without touching PostgreSQL."""
        missing = self.run_path / "does-not-exist.zip"
        stdout, stderr = self.dispatch_command("restore", self.database_name, str(missing))
        self.assertIn("Invalid dump file", stdout + stderr)

    def test_91_kill_not_running(self):
        """`odev kill` should fail when the database process is not running."""
        _, stderr = self.dispatch_command("kill", self.database_name)
        self.assertIn("is not running", stderr)

    def test_92_deploy_requires_running_database(self):
        """`odev deploy` should refuse when the local database is not running."""
        module_root = self.run_path / "fake_module"
        module_root.mkdir(parents=True, exist_ok=True)
        (module_root / "__manifest__.py").write_text("{'name': 'fake', 'version': '1.0'}", encoding="utf-8")
        stdout, stderr = self.dispatch_command("deploy", self.database_name, str(module_root))
        self.assertIn("must be running", stdout + stderr)

    def test_93_standardize_requires_odoo_database(self):
        """`odev standardize` should reject a non-Odoo (e.g. bare) database."""
        bare_name = f"{self.run_name}-bare-std"
        try:
            self.dispatch_command("create", "--bare", bare_name)
            self.assertDatabaseExist(bare_name)
            _, stderr = self.dispatch_command("standardize", bare_name)
            self.assertIn("must be an Odoo database", stderr)
        finally:
            db = LocalDatabase(bare_name)
            if db.exists:
                db.drop()

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
            stdout, _ = self.dispatch_command(
                "delete",
                "--expression",
                "^odev-test-[a-z0-9]{8}",
                "--include-whitelisted",
            )

        self.assertDatabaseNotExist(self.database_name)
        self.assertDatabaseNotExist(self.template_name)
        self.assertIn("You are about to delete the following databases:", stdout)
        self.assertRegex(stdout, r"Deleted \d+ databases")
