from subprocess import CompletedProcess
import re

from odev.common import string

from odev.common.databases import LocalDatabase
from odev.common.odoobin import OdoobinProcess
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
        self.assertEqual(len(stdout.splitlines()), 9)

        totals = (0, 0, 0)

        for line in stdout.splitlines()[3:~2]:
            numbers_match = re.search(r"\s+(\d+) +(\d+) +(\d+)", line)
            assert numbers_match is not None
            numbers = numbers_match.groups()
            totals = tuple(int(a) + int(b) for a, b in zip(totals, numbers))

        self.assertEqual(totals, (2237, 525, 1712))

    def test_02_cloc_csv(self):
        """Command `odev cloc --csv` should display line of codes count by module in csv format."""
        with self.patch(ODOOBIN_PATH, "run", CompletedProcess(args=["cloc"], returncode=0, stdout=self.CLOC_RESULT)):
            stdout, _ = self.dispatch_command("cloc", self.database.name, "--csv")

        self.assertIn("test_module_01", stdout)
        self.assertEqual(len(stdout.strip().splitlines()), 5)

        totals = (0, 0, 0)

        for line in stdout.splitlines()[1:~1]:
            numbers_match = re.search(r",(\d+),(\d+),(\d+)", line)
            assert numbers_match is not None
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

        self.dispatch_command("create", self.create_database_name)

        database = LocalDatabase(self.create_database_name)
        self.assertTrue(database.exists)
        self.assertRegex(
            self.Popen.all_calls[-1].args[0],
            rf"odoo-bin -d {self.create_database_name} --addons-path [a-z0-9. \-/,]+ --init base --stop-after-init",
            "The odoo-bin executable should be run with the correct arguments.",
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


class TestCommandDatabaseTest(OdevCommandTestCase):
    """Command `odev test` should run tests on a database."""

    def test_01_test(self):
        """Command `odev test` should run tests on a database."""
        # with self.patch(ODOOBIN_PATH, "run", CompletedProcess(args=["test"], returncode=0)):
        stdout, _ = self.dispatch_command("test", self.database.name, "--modules", "base")

        self.assertTrue(self.database.exists)
        self.assertRegex(stdout, rf"Created database '{self.database.name}_[a-z0-9]{{8}}'")
        self.assertIn("No failing tests", stdout)
        self.assertRegex(stdout, rf"Dropped database '{self.database.name}_[a-z0-9]{{8}}'")
        self.assertRegex(
            self.Popen.all_calls[-1].args[0],
            rf"odoo-bin -d {self.database.name}_[a-z0-9]{{8}} --addons-path [a-z0-9.\s\-/,]* --log-level info --stop-after-init --test-enable --init base",
        )
