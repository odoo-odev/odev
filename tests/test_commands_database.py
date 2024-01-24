import shutil
from typing import cast
from pathlib import Path

from testfixtures import Replacer
from testfixtures.popen import MockPopen

from odev.common.databases import LocalDatabase
from odev.common.odev import logger
from odev.common.odoobin import OdoobinProcess
from odev.common.python import PythonEnv
from odev.common.string import suid
from odev.common.version import OdooVersion
from tests.fixtures import CaptureOutput, OdevTestCase


class TestDatabaseCommands(OdevTestCase):
    """Run unit tests on instances of a database command."""

    db_name = f"odev-unit-test-{suid()}"
    database = LocalDatabase(db_name)
    venv = PythonEnv()
    odoobin_path = Path("/tmp/odev-test/odoo-bin")

    @classmethod
    def setUpClass(cls):
        cls.Popen = MockPopen()
        cls.Popen.set_default(stdout=b"")
        cls.replacer = Replacer()
        cls.replacer.replace("subprocess.Popen", cls.Popen)
        cls.replacer.replace("odev.common.bash.Popen", cls.Popen)
        cls.addClassCleanup(cls.replacer.restore)
        if not cls.odoobin_path.exists():
            cls.odoobin_path.parent.mkdir(parents=True, exist_ok=True)
            cls.odoobin_path.touch()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.database.venv:
            shutil.rmtree(cls.database.venv)
        if cls.database.exists:
            cls.database.drop()
        if cls.odoobin_path.exists():
            cls.odoobin_path.unlink()
            cls.odoobin_path.parent.rmdir()
        return super().tearDownClass()

    def test_command_create(self):
        """Test creating a database using the create command."""
        self.odev.config.reset("paths", "repositories")

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

        self.assertIsInstance(command.database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command.database).name, self.db_name, "The database name should be set correctly."
        )

        with LocalDatabase(self.db_name) as local_database, local_database.psql().nocache():
            self.assertTrue(local_database.exists, "The database should exist on the local system.")

        store_database = (self.odev.store.databases.get(local_database),)
        self.assertIsNotNone(store_database, "The database should be stored in the database store.")

    def test_command_test(self):
        """Test running tests on a database using the test command."""
        with self.patch(OdoobinProcess, "clone_repositories", return_value=None):
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

        self.assertIsInstance(command.database, LocalDatabase, "The database should be an instance of LocalDatabase.")
        self.assertEqual(
            cast(LocalDatabase, command.database).name, self.db_name, "The database name should be set correctly."
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
