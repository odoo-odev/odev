import re
from subprocess import CompletedProcess

from odev.common import string
from odev.common.databases import LocalDatabase
from tests.fixtures import OdevCommandTestCase


ODOOBIN_PATH = "odev.common.odoobin.OdoobinProcess"


class TestCommandDatabaseCloc(OdevCommandTestCase):
    """Command `odev cloc` should print line of codes count for modules installed in a database."""

    CLOC_RESULT = string.normalize_indent(
        """
        Odoo cloc                                                   Line   Other    Code
        --------------------------------------------------------------------------------
        test_module_01                                               335      61     274
        test_module_02                                              1095     273     822
        test_module_03                                               807     191     616
        --------------------------------------------------------------------------------
                                                                    2237     525    1712
        """
    ).encode()

    def test_01_cloc(self):
        """Command `odev cloc` should display line of codes count by module."""
        with self.patch(ODOOBIN_PATH, "run", CompletedProcess(args=["cloc"], returncode=0, stdout=self.CLOC_RESULT)):
            stdout, _ = self.dispatch_command("cloc", self.database.name)

        self.assertIn("test_module_01", stdout)
        self.assertEqual(len(stdout.splitlines()), 8)

        totals = (0, 0, 0)

        for line in stdout.splitlines()[:~1]:
            numbers_match = re.search(r"\s+(\d+) +(\d+) +(\d+)", line)
            if not numbers_match:
                continue
            numbers = numbers_match.groups()
            totals = tuple(int(a) + int(b) for a, b in zip(totals, numbers))

        self.assertEqual(totals, (2237, 525, 1712))

    def test_02_cloc_csv(self):
        """Command `odev cloc --csv` should display line of codes count by module in csv format."""
        with self.patch(ODOOBIN_PATH, "run", CompletedProcess(args=["cloc"], returncode=0, stdout=self.CLOC_RESULT)):
            stdout, _ = self.dispatch_command("cloc", self.database.name, "--csv")

        self.assertIn("test_module_01", stdout)
        self.assertEqual(len(stdout.strip().splitlines()), 6)

        totals = (0, 0, 0)

        for line in stdout.splitlines()[:~1]:
            numbers_match = re.search(r",(\d+),(\d+),(\d+)", line)
            if not numbers_match:
                continue
            numbers = numbers_match.groups()
            totals = tuple(int(a) + int(b) for a, b in zip(totals, numbers))

        self.assertEqual(totals, (2237, 525, 1712))


class TestCommandDatabaseCreate(OdevCommandTestCase):
    """Command `odev create` should create a new database."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_database_name = f"{cls.run_name}-create"

    def tearDown(self):
        super().tearDown()

        for name in (self.create_database_name, f"{self.create_database_name}:template"):
            database = LocalDatabase(name)

            if database.exists:
                database.drop()

    def test_01_create_bare(self):
        """Command `odev create --bare` should create a new database but should not initialize it with Odoo."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        self.dispatch_command("create", self.create_database_name, "--bare")

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertFalse(database.is_odoo)
        self.assertIsNone(self.odev.store.databases.get(database))

    def test_02_create_odoo(self):
        """Command `odev create` should create a new database and initialize it with Odoo."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        with self.patch("odev.common.bash", "stream", []) as mock_stream:
            stdout, _ = self.dispatch_command("create", self.create_database_name)

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertIn("Running 'odoo-bin' in version master on database", stdout)
        mock_stream.assert_called_once()
        self.assertRegex(
            mock_stream.call_args[0][0],
            rf"odoo-bin --database {self.create_database_name} "
            r"--addons-path [a-z0-9. \-/,]+ --init base --stop-after-init",
        )

    def test_03_create_from_template(self):
        """Command `odev create` should create a new database from an existing template."""
        template_database = self.create_odoo_database(f"{self.create_database_name}:template")
        self.assertTrue(template_database.exists)
        self.assertTrue(template_database.is_odoo)

        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        if template_database.connector:
            template_database.connector.disconnect()

        with self.patch(ODOOBIN_PATH, "run") as mock_odoobin_run:
            self.dispatch_command("create", self.create_database_name, "--template", template_database.name)

        mock_odoobin_run.assert_not_called()

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertTrue(database.is_odoo)

    def test_04_create_new_template(self):
        """Command `odev create` should create a new template database."""
        database = self.create_odoo_database(f"{self.create_database_name}")
        self.assertTrue(database.exists)
        self.assertTrue(database.is_odoo)

        template_database = LocalDatabase(f"{self.create_database_name}:template")
        self.assertFalse(template_database.exists)

        self.dispatch_command("create", self.create_database_name, "--create-template")

        template_database = LocalDatabase(f"{self.create_database_name}:template")
        self.assertTrue(template_database.exists)

    def test_05_overwrite(self):
        """Command `odev create` should overwrite an existing database."""
        database = self.create_odoo_database(self.create_database_name)
        self.assertTrue(database.exists)

        stdout, _ = self.dispatch_command("create", self.create_database_name, "--force")

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertIn(f"Database '{self.create_database_name}' already exists", stdout)

    def test_06_with_venv(self):
        """Command `odev create` should create a new database with a specific virtual environment."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        self.dispatch_command("create", self.create_database_name, "--venv", self.venv.name)

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertEqual(database.venv.name, self.venv.name)

    def test_07_with_version(self):
        """Command `odev create` should create a new database with a specific Odoo version."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        stdout, _ = self.dispatch_command("create", self.create_database_name, "--version", "17.0")

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertIn("Running 'odoo-bin' in version 17.0 on database", stdout)
        self.assertEqual(database.venv.name, "17.0")

    def test_08_with_worktree(self):
        """Command `odev create` should create a new database with a specific worktree."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        stdout, _ = self.dispatch_command(
            "create", self.create_database_name, "--worktree", f"{self.run_name}-worktree"
        )

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertIn("Running 'odoo-bin' in version master on database", stdout)
        self.assertEqual(database.worktree, f"{self.run_name}-worktree")

    def test_09_with_version_and_venv(self):
        """Command `odev create` should create a new database with a specific Odoo version and virtual environment."""
        database = LocalDatabase(self.create_database_name)
        self.assertFalse(database.exists)

        stdout, _ = self.dispatch_command(
            "create", self.create_database_name, "--version", "17.0", "--venv", self.venv.name
        )

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertIn("Running 'odoo-bin' in version 17.0 on database", stdout)
        self.assertEqual(database.venv.name, self.venv.name)


class TestCommandDatabaseTest(OdevCommandTestCase):
    """Command `odev test` should run tests on a database."""

    def test_01_test(self):
        """Command `odev test` should run tests on a database."""
        with self.patch("odev.common.bash", "stream", []) as mock_stream:
            stdout, _ = self.dispatch_command("test", self.database.name, "--modules", "base")

        self.assertTrue(self.database.exists)
        self.assertRegex(stdout, rf"Created database '{self.database.name}_[a-z0-9]{{8}}'")
        self.assertIn("No failing tests", stdout)
        self.assertRegex(stdout, rf"Dropped database '{self.database.name}_[a-z0-9]{{8}}'")
        mock_stream.assert_called_once()
        self.assertRegex(
            mock_stream.call_args[0][0],
            rf"odoo-bin --database {self.database.name}_[a-z0-9]{{8}} "
            r"--addons-path [a-z0-9.\s\-/,]* --log-level info --stop-after-init --test-enable --init base",
        )


class TestCommandDatabaseDelete(OdevCommandTestCase):
    """Command `odev delete` should delete a database."""

    def setUp(self):
        super().setUp()
        self.delete_database = self.create_odoo_database(f"{self.run_name}-delete")

    def tearDown(self):
        super().tearDown()

        if self.delete_database.exists:
            self.delete_database.drop()

    def test_01_delete_database(self):
        """Command `odev delete` should delete a database if a name is provided."""
        self.assertTrue(self.delete_database.exists)

        stdout, _ = self.dispatch_command("delete", self.delete_database.name)

        self.assertFalse(self.delete_database.exists)
        self.assertIn(f"Dropped database '{self.delete_database.name}'", stdout)

    def test_02_delete_non_existent(self):
        """Command `odev delete` should display an error message when trying to delete a non-existent database."""
        self.delete_database.drop()
        self.assertFalse(self.delete_database.exists)

        _, stderr = self.dispatch_command("delete", self.delete_database.name)

        self.assertFalse(self.delete_database.exists)
        self.assertIn(f"No non-whitelisted database found named '{self.delete_database.name}'", stderr)

    def test_03_delete_no_filter(self):
        """Command `odev delete` should not delete databases if no filter (database or expression) are provided."""
        self.assertTrue(self.delete_database.exists)

        _, stderr = self.dispatch_command("delete")

        self.assertTrue(self.delete_database.exists)
        self.assertIn("Arguments database and expression are mutually exclusive and at least one is required", stderr)

    def test_04_delete_expression(self):
        """Command `odev delete` should delete databases matching a regular expression."""
        self.assertTrue(self.delete_database.exists)

        with self.patch("odev.common.console.Console", "confirm", True):
            stdout, _ = self.dispatch_command("delete", "-e", ".*-delete$")

        self.assertFalse(self.delete_database.exists)
        self.assertIn(f"You are about to delete the following databases: '{self.delete_database.name}'", stdout)
        self.assertIn("Deleted 1 databases", stdout)
