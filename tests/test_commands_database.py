from contextlib import contextmanager
import shutil
from subprocess import CompletedProcess
from typing import cast
from pathlib import Path
import re

from odev.common import string
from odev.common.databases import LocalDatabase
from odev.common.odev import logger
from odev.common.odoobin import OdoobinProcess
from odev.common.python import PythonEnv
from odev.common.string import suid
from odev.common.version import OdooVersion
from tests.fixtures import CaptureOutput, OdevCommandTestCase


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

class TestDatabaseCommands(OdevCommandTestCase):
    """Run unit tests on instances of a database command."""

    db_name = f"odev-unit-test-{suid()}"
    database = LocalDatabase(db_name)
    venv = PythonEnv()
    odoobin_path = Path("/tmp/odev-test/odoo-bin")

    def setUp(self):
        if not self.odoobin_path.exists():
            self.odoobin_path.parent.mkdir(parents=True, exist_ok=True)
            self.odoobin_path.touch()
        self.odev.config.reset("paths", "repositories")
        return super().setUp()

    def tearDown(self) -> None:
        template = LocalDatabase(f"{self.db_name}:template")
        if template.exists:
            template.drop()
        if self.database.exists:
            self.database.drop()
        if self.odoobin_path.exists():
            self.odoobin_path.unlink()
            self.odoobin_path.parent.rmdir()
        return super().tearDown()

    @contextmanager
    def create_test_database(self, odoo: bool = True):
        if not self.database.exists:
            self.database.create()

        if odoo:
            self.database.create_table("ir_config_parameter", {"key": "varchar(255)", "value": "varchar(255)"})
            self.database.create_table("res_users_log", {"create_date": "timestamp"})
            self.database.create_table(
                "ir_module_module",
                {
                    "name": "varchar(255)",
                    "state": "varchar(255)",
                    "latest_version": "varchar(255)",
                    "license": "varchar(255)",
                },
            )
            self.database.query(
                """
                INSERT INTO ir_module_module (name, state, latest_version, license)
                VALUES ('base', 'installed', '17.0.1.0.0', 'OPL-1')
                """
            )

        yield

        if self.database.exists:
            self.database.drop()

    def test_command_cloc_01(self):
        """Test running cloc on a database using the odoo-bin cloc command."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None), self.create_test_database():
            command = self.setup_command("cloc", self.db_name)

            with (
                CaptureOutput() as output,
                self.patch(OdoobinProcess, "run", return_value=CompletedProcess(args=["cloc"], returncode=0, stdout=CLOC_RESULT)),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        self.assertIn("test_module_01", output.stdout, "The output should contain the first module.")
        self.assertEqual(len(output.stdout.splitlines()), 9, "The output should contain 9 lines, including titles and totals.")

        totals = (0, 0, 0)

        for line in output.stdout.splitlines()[3:~2]:
            numbers = re.search(r"\s+(\d+) +(\d+) +(\d+)", line).groups()
            totals = tuple(int(a) + int(b) for a, b in zip(totals, numbers))

        self.assertEqual(totals, (2237, 525, 1712), "The totals should be calculated correctly.")

    def test_command_cloc_02_csv(self):
        """Test running cloc on a database using the odoo-bin cloc command and output as CSV."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None), self.create_test_database():
            command = self.setup_command("cloc", f"{self.db_name} --csv")

            with (
                CaptureOutput() as output,
                self.patch(OdoobinProcess, "run", return_value=CompletedProcess(args=["cloc"], returncode=0, stdout=CLOC_RESULT)),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        self.assertIn("test_module_01", output.stdout, "The output should contain the first module.")
        self.assertEqual(len(output.stdout.rstrip().splitlines()), 5, "The output should contain 5 lines, including titles and totals.")

        totals = (0, 0, 0)

        for line in output.stdout.splitlines()[1:~1]:
            numbers = re.search(r",(\d+),(\d+),(\d+)", line).groups()
            totals = tuple(int(a) + int(b) for a, b in zip(totals, numbers))

        self.assertEqual(totals, (2237, 525, 1712), "The totals should be calculated correctly.")

    def test_command_create_01_bare(self):
        """Test creating a database using the create command, do not initialize Odoo."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None):
            command = self.setup_command("create", f"{self.db_name} --bare")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command._database).name, self.db_name, "The database name should be set correctly."
        )

        with LocalDatabase(self.db_name) as local_database, local_database.psql().nocache():
            self.assertTrue(local_database.exists, "The database should exist on the local system.")
            self.assertFalse(local_database.is_odoo, "The database should not be an Odoo database.")

        store_database = (self.odev.store.databases.get(local_database),)
        self.assertIsNotNone(store_database, "The database should be stored in the database store.")

    def test_command_create_02_odoo(self):
        """Test creating a database using the create command, initialize Odoo with the latest version."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None):
            command = self.setup_command("create", f"{self.db_name} --version master -f")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        self.assertRegex(
            self.Popen.all_calls[-1].args[0],
            rf"odoo-bin -d {self.db_name} --addons-path [a-z0-9. \-/,]+ --init base --stop-after-init",
            "The odoo-bin executable should be run with the correct arguments.",
        )

        self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command._database).name, self.db_name, "The database name should be set correctly."
        )

        with LocalDatabase(self.db_name) as local_database, local_database.psql().nocache():
            self.assertTrue(local_database.exists, "The database should exist on the local system.")

        store_database = (self.odev.store.databases.get(local_database),)
        self.assertIsNotNone(store_database, "The database should be stored in the database store.")

    def test_command_create_03_new_template(self):
        """Test creating a database using the create command, create a new template from an existing database."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None):
            command = self.setup_command("create", f"{self.db_name} --version master --create-template")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        db_name = f"{self.db_name}:template"

        self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command._database).name, db_name, "The database name should be set correctly."
        )

        with LocalDatabase(db_name) as local_database, local_database.psql().nocache():
            self.assertTrue(local_database.exists, "The database should exist on the local system.")

        store_database = (self.odev.store.databases.get(local_database),)
        self.assertIsNotNone(store_database, "The database should be stored in the database store.")

    def test_command_create_04_from_template(self):
        """Test creating a database using the create command, create a new database from an existing template."""

        template_database = LocalDatabase(f"{self.db_name}:template")

        if template_database.exists:
            template_database.drop()

        template_database.create()
        template_database.filestore.path.mkdir(parents=True, exist_ok=True)
        self.database.filestore.path.mkdir(parents=True, exist_ok=True)

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None):
            command = self.setup_command("create", f"{self.db_name} --version master --template {self.db_name}:template")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

        self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command._database).name, self.db_name, "The database name should be set correctly."
        )

        with LocalDatabase(self.db_name) as local_database, local_database.psql().nocache():
            self.assertTrue(local_database.exists, "The database should exist on the local system.")

        store_database = (self.odev.store.databases.get(local_database),)
        self.assertIsNotNone(store_database, "The database should be stored in the database store.")

        template_database.filestore.path.rmdir()
        self.database.filestore.path.rmdir()

    def test_command_create_05_overwrite(self):
        """Test creating a database using the create command, with a database that already exists."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None), self.create_test_database():
            command = self.setup_command("create", f"{self.db_name} --bare")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
            ):
                command.run()

            self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
            self.assertEqual(
                cast(LocalDatabase, command._database).name, self.db_name, "The database name should be set correctly."
            )

            with LocalDatabase(self.db_name) as local_database, local_database.psql().nocache():
                self.assertTrue(local_database.exists, "The database should exist on the local system.")
                self.assertFalse(local_database.is_odoo, "The database should not be an Odoo database.")

            store_database = (self.odev.store.databases.get(local_database),)
            self.assertIsNotNone(store_database, "The database should be stored in the database store.")

    def test_command_test_01(self):
        """Test running tests on a database using the test command."""

        with self.patch(OdoobinProcess, "clone_repositories", return_value=None), self.create_test_database():
            command = self.setup_command("test", f"{self.db_name} --modules base")

            with (
                CaptureOutput(),
                self.patch(logger, "warning"),
                self.patch(self.odev.console, "confirm", return_value=True),
                self.patch(OdoobinProcess, "prepare_odoobin", return_value=None),
                self.patch(OdoobinProcess, "addons_contain_debugger", return_value=None),
                self.patch_property(OdoobinProcess, "pid", return_value=None),
                self.patch_property(OdoobinProcess, "odoo_addons_paths", return_value=[]),
                self.patch_property(OdoobinProcess, "odoobin_path", return_value=self.odoobin_path),
                self.patch_property(LocalDatabase, "version", return_value=OdooVersion("master")),
                self.patch_property(LocalDatabase, "venv", return_value=self.venv.path),
            ):
                command.run()
                command.cleanup()

            self.assertRegex(
                self.Popen.all_calls[-1].args[0],
                rf"odoo-bin -d {self.db_name}_[a-z0-9]{{8}} --addons-path [a-z0-9. \-/,]+ --stop-after-init --test-enable --init base",
                "The odoo-bin executable should be run with the correct arguments.",
            )

            self.assertIsInstance(command._database, LocalDatabase, "The database should be an instance of LocalDatabase.")
            self.assertEqual(
                cast(LocalDatabase, command._database).name, self.db_name, "The database name should be set correctly."
            )

            local_database = LocalDatabase(self.db_name)
            self.assertTrue(local_database.exists, "The database should still exist on the local system.")

            store_database = (self.odev.store.databases.get(local_database),)
            self.assertIsNotNone(store_database, "The database should be stored in the database store.")

            self.assertIsInstance(
                command.test_database, LocalDatabase, "The test database should be an instance of LocalDatabase."
            )
            self.assertRegex(
                cast(LocalDatabase, command.test_database).name,
                rf"{self.db_name}_[a-z0-9]{{8}}",
                "The database name should be set correctly.",
            )

            local_database = LocalDatabase(command.test_database.name)
            self.assertFalse(local_database.exists, "The database should have been removed from the local system.")

            store_database = self.odev.store.databases.get(local_database)
            self.assertIsNone(store_database, "The database should have been removed from the database store.")
