import re
import shlex
from pathlib import Path
from subprocess import CompletedProcess, Popen
from time import sleep

from odev.common import string
from odev.common.databases import LocalDatabase
from tests.fixtures import OdevCommandRunDatabaseTestCase, OdevCommandTestCase
from tests.fixtures.matchers import OdoobinMatch


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
        cls.template_database_name = f"{cls.create_database_name}:template"

    def tearDown(self):
        super().tearDown()

        for name in (self.create_database_name, self.template_database_name):
            database = LocalDatabase(name)

            if database.venv.exists and not database.venv._global:
                database.venv.remove()

            for worktree in database.worktrees:
                worktree.connector.remove_worktree(worktree.path)

            if database.exists:
                database.drop()

    def test_01_create_bare(self):
        """Command `odev create --bare` should create a new database but should not initialize it with Odoo."""
        self.assert_database(self.create_database_name, exists=False)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", self.create_database_name, "--bare")
            stream.assert_not_called()

        self.assert_database(self.create_database_name, exists=True, is_odoo=False)

    def test_02_create_odoo(self):
        """Command `odev create` should create a new database and initialize it with Odoo."""
        self.assert_database(self.create_database_name, exists=False)

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "create", self.create_database_name, "--version", "17.0", "--without-demo", "all"
            )
            stream.assert_called_with(
                OdoobinMatch(
                    self.create_database_name,
                    ["--without-demo", "all", "--init", "base", "--stop-after-init"],
                )
            )

        self.assertIn("Running 'odoo-bin' in version '17.0' on database", stdout)
        self.assert_database(self.create_database_name, version="17.0")

    def test_03_create_from_template(self):
        """Command `odev create` should create a new database from an existing template."""
        template_database = self.create_odoo_database(self.template_database_name)
        self.assert_database(template_database.name, is_odoo=True)
        self.assert_database(self.create_database_name, exists=False)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", self.create_database_name, "--template", template_database.name)
            stream.assert_not_called()

        self.assert_database(self.create_database_name, version=str(template_database.version))

    def test_04_create_new_template(self):
        """Command `odev create` should create a new template database."""
        database = self.create_odoo_database(self.create_database_name)
        self.assert_database(database.name, is_odoo=True)
        self.assert_database(self.template_database_name, exists=False)

        with self.wrap("odev.common.bash", "stream") as stream:
            self.dispatch_command("create", self.create_database_name, "--create-template")
            stream.assert_not_called()

        self.assert_database(self.template_database_name, version=str(database.version))

    def test_05_overwrite(self):
        """Command `odev create` should overwrite an existing database."""
        database = self.create_odoo_database(self.create_database_name)
        database_version = database.version
        self.assert_database(database.name, is_odoo=True)

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "create", self.create_database_name, "--force", "--version", "16.0", "--without-demo", "all"
            )
            stream.assert_called_with(
                OdoobinMatch(
                    self.create_database_name,
                    ["--without-demo", "all", "--init", "base", "--stop-after-init"],
                )
            )

        self.assert_database(database.name, is_odoo=True)
        self.assertNotEqual(database_version, LocalDatabase(database.name).version)
        self.assertIn(f"Database '{self.create_database_name}' already exists", stdout)

    def test_06_with_venv(self):
        """Command `odev create` should create a new database with a specific virtual environment."""
        self.assert_database(self.create_database_name, is_odoo=False)
        self.dispatch_command(
            "create", self.create_database_name, "--venv", self.venv.name, "--version", "17.0", "--without-demo", "all"
        )
        self.assert_database(self.create_database_name, is_odoo=True)
        self.assertEqual(LocalDatabase(self.create_database_name).venv.name, self.venv.name)

    def test_07_with_version(self):
        """Command `odev create` should create a new database with a specific Odoo version."""
        self.assert_database(self.create_database_name, is_odoo=False)
        self.dispatch_command("create", self.create_database_name, "--version", "17.0", "--without-demo", "all")
        self.assert_database(self.create_database_name, is_odoo=True, version="17.0")
        database = LocalDatabase(self.create_database_name)
        self.assertEqual(database.venv.name, "17.0")
        self.assertTrue(Path(database.venv.path).is_dir())

    def test_08_with_worktree(self):
        """Command `odev create` should create a new database with a specific worktree."""
        self.assert_database(self.create_database_name, is_odoo=False)
        self.dispatch_command(
            "create", self.create_database_name, "--worktree", "test", "--version", "17.0", "--without-demo", "all"
        )
        self.assert_database(self.create_database_name, is_odoo=True)
        database = LocalDatabase(self.create_database_name)
        self.assertEqual(database.worktree, "test")
        self.assertTrue(Path(self.odev.worktrees_path / (database.worktree or "")).is_dir())


class TestCommandDatabaseTest(OdevCommandTestCase):
    """Command `odev test` should run tests on a database."""

    def test_01_test(self):
        """Command `odev test` should run tests on a database."""
        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("test", self.database.name, "--tags", ":TestSafeEval.test_expr")
            stream.assert_called_with(
                OdoobinMatch(
                    self.database.name,
                    ["--stop-after-init", "--test-enable", "--test-tags", ":TestSafeEval.test_expr", "--init", "base"],
                )
            )

        self.assert_database(self.database.name, is_odoo=True)
        self.assertRegex(stdout, rf"Created database '{self.database.name}_[a-z0-9]{{8}}'")
        self.assertIn("No failing tests", stdout)
        self.assertRegex(stdout, rf"Dropped database '{self.database.name}_[a-z0-9]{{8}}'")


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
        self.assert_database(self.delete_database.name, exists=True)
        stdout, _ = self.dispatch_command("delete", self.delete_database.name)
        self.assertIn(f"Dropped database '{self.delete_database.name}'", stdout)
        self.assert_database(self.delete_database.name, exists=False)

    def test_02_delete_non_existent(self):
        """Command `odev delete` should display an error message when trying to delete a non-existent database."""
        self.delete_database.drop()
        self.assert_database(self.delete_database.name, exists=False)
        _, stderr = self.dispatch_command("delete", self.delete_database.name)
        self.assert_database(self.delete_database.name, exists=False)
        self.assertIn(f"No non-whitelisted database found named '{self.delete_database.name}'", stderr)

    def test_03_delete_no_filter(self):
        """Command `odev delete` should not delete databases if no filter (database or expression) are provided."""
        self.assert_database(self.delete_database.name, exists=True)
        _, stderr = self.dispatch_command("delete")
        self.assert_database(self.delete_database.name, exists=True)
        self.assertIn("Arguments database and expression are mutually exclusive and at least one is required", stderr)

    def test_04_delete_expression(self):
        """Command `odev delete` should delete databases matching a regular expression."""
        self.assert_database(self.delete_database.name, exists=True)

        with self.patch("odev.common.console.Console", "confirm", True):
            stdout, _ = self.dispatch_command("delete", "-e", ".*-delete$")

        self.assert_database(self.delete_database.name, exists=False)
        self.assertIn(f"You are about to delete the following databases: '{self.delete_database.name}'", stdout)
        self.assertIn("Deleted 1 databases", stdout)


class TestCommandDatabaseRun(OdevCommandRunDatabaseTestCase):
    """Command `odev run` should run Odoo in a database."""

    def test_01_run(self):
        """Command `odev run` should run Odoo in a database."""
        self.assert_database(self.database.name, is_odoo=True)

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command("run", self.database.name, "--stop-after-init")
            stream.assert_called_with(OdoobinMatch(self.database.name, ["--stop-after-init"]))

        self.assert_database(self.database.name, is_odoo=True)
        self.assertIn(f"Running 'odoo-bin' in version '17.0' on database '{self.database.name}'", stdout)

    def test_02_run_from_template(self):
        """Command `odev run` should run Odoo in a database from a template."""
        self.assert_database(self.database.name, is_odoo=True)
        self.dispatch_command("create", self.database.name, "--create-template")
        template_name = f"{self.database.name}:template"
        self.assert_database(template_name, is_odoo=True)
        self.database.query("CREATE TABLE test_table (id SERIAL PRIMARY KEY);")
        self.assertTrue(self.database.table_exists("test_table"))

        with self.wrap("odev.common.bash", "stream") as stream:
            stdout, _ = self.dispatch_command(
                "run", self.database.name, "--stop-after-init", "--template", template_name
            )
            stream.assert_called_with(OdoobinMatch(self.database.name, ["--stop-after-init"]))

        self.assert_database(self.database.name, is_odoo=True)
        self.assertFalse(self.database.table_exists("test_table"))
        self.assertIn(f"Running 'odoo-bin' in version '17.0' on database '{self.database.name}'", stdout)
        LocalDatabase(template_name).drop()

    def test_03_run_from_invalid_template(self):
        """Command `odev run` should not delete the existing database if the template does not exist."""
        self.assert_database(self.database.name, is_odoo=True)
        template_name = f"{self.database.name}:template"
        self.assert_database(template_name, exists=False)
        self.database.query("CREATE TABLE test_table (id SERIAL PRIMARY KEY);")
        self.assertTrue(self.database.table_exists("test_table"))
        stdout, _ = self.dispatch_command("run", self.database.name, "--stop-after-init", "--template", template_name)
        self.assert_database(self.database.name, is_odoo=True)
        self.assertTrue(self.database.table_exists("test_table"))
        self.assertNotIn(f"Running 'odoo-bin' in version '17.0' on database '{self.database.name}'", stdout)


class TestCommandDatabaseKill(OdevCommandRunDatabaseTestCase):
    """Command `odev kill` should kill Odoo processes in a database."""

    def test_01_kill(self):
        """Command `odev kill` should kill Odoo processes in a database."""
        self.assert_database(self.database.name, is_odoo=True)
        assert self.database.process is not None
        command = string.strip_styles(self.database.process.format_command().replace("\\\n", " "))
        Popen(shlex.split(command), start_new_session=True)

        seconds, elapsed = 2, 0
        while not self.database.running and elapsed < 30:
            sleep(seconds)
            elapsed += seconds

        self.assertTrue(self.database.running)
        self.dispatch_command("kill", self.database.name)
        self.assert_database(self.database.name, is_odoo=True)
        self.assertFalse(self.database.running)
