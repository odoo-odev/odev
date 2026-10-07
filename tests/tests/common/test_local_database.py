from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, PropertyMock

from odev.commands.database.delete import DeleteCommand
from odev.common.databases import LocalDatabase
from odev.common.store.tables.databases import DatabaseInfo
from odev.common.version import OdooVersion

from tests.fixtures import OdevTestCase


class TestNeutralizeScripts(OdevTestCase):
    """Neutralization must pick up the `data/neutralize.sql` scripts shipped by custom modules."""

    def setUp(self):
        super().setUp()
        self.addons_path = self.res_path / "repositories" / "test" / "test-addons"

    def make_database(self, addons_paths: list[Path] | None = None) -> LocalDatabase:
        database = LocalDatabase.__new__(LocalDatabase)
        database._framework = self.odev
        database._process = MagicMock()
        database._process.additional_addons_paths = [self.addons_path] if addons_paths is None else addons_paths
        return database

    def neutralize_scripts(
        self,
        installed_modules: list[str],
        addons_paths: list[Path] | None = None,
        version: str = "18.0",
    ) -> list[Path]:
        database = self.make_database(addons_paths)

        with (
            self.patch_property(LocalDatabase, "installed_modules", installed_modules),
            self.patch_property(LocalDatabase, "process", database._process),
            self.patch_property(LocalDatabase, "version", OdooVersion(version)),
        ):
            return database._neutralize_scripts()

    def test_custom_module_script_is_collected(self):
        """Regression for #98: the module scripts were filtered against the *addons directory*
        names rather than the module names, so no custom script was ever collected.
        """
        scripts = self.neutralize_scripts(["base", "addon_01"])
        self.assertEqual(
            scripts,
            [
                self.odev.static_path / "neutralize-pre.sql",
                self.addons_path / "addon_01" / "data" / "neutralize.sql",
                self.odev.static_path / "neutralize-post.sql",
            ],
        )

    def test_module_without_script_is_skipped(self):
        scripts = self.neutralize_scripts(["addon_02"], addons_paths=[self.addons_path / "submodule"])
        self.assertEqual(
            scripts,
            [
                self.odev.static_path / "neutralize-pre.sql",
                self.odev.static_path / "neutralize-post.sql",
            ],
        )

    def test_module_not_installed_is_skipped(self):
        scripts = self.neutralize_scripts(["base"])
        self.assertNotIn(self.addons_path / "addon_01" / "data" / "neutralize.sql", scripts)

    def test_no_addons_paths_yields_static_scripts_only(self):
        scripts = self.neutralize_scripts(["addon_01"], addons_paths=[])
        self.assertEqual(
            scripts,
            [
                self.odev.static_path / "neutralize-pre.sql",
                self.odev.static_path / "neutralize-post.sql",
            ],
        )

    def test_older_versions_get_the_legacy_script(self):
        scripts = self.neutralize_scripts(["base"], version="14.0")
        self.assertIn(self.odev.static_path / "neutralize-post-before-15.0.sql", scripts)


class TestLocalDatabaseCost(OdevTestCase):
    """Commands build a database object for every database they look at: doing so has to stay cheap."""

    def stored_info(self, whitelisted: bool) -> DatabaseInfo:
        """Build the values the data store would hold for a database.

        :param whitelisted: Whether the database is saved as whitelisted.
        :return: The saved values of the database.
        :rtype: DatabaseInfo
        """
        return DatabaseInfo(
            name="test-cost",
            platform="local",
            virtualenv="",
            arguments="",
            whitelisted=whitelisted,
            repository=None,
            branch=None,
            worktree="",
            url="",
        )

    def test_01_building_a_database_does_not_save_it(self):
        """Building a database object should read the data store and leave it as it is."""
        with (
            self.patch_property(LocalDatabase, "is_odoo", value=True),
            self.patch(self.odev.store.databases, "get", self.stored_info(whitelisted=True)),
            self.patch(self.odev.store.databases, "set") as patched_set,
        ):
            database = LocalDatabase("test-cost")

        patched_set.assert_not_called()
        self.assertTrue(database._whitelisted, "the saved flag should be kept for the next time the database is saved")

    def test_02_unknown_database_is_saved_once(self):
        """A database the data store knows nothing about should be saved, so that what it uses is known."""
        with (
            self.patch_property(LocalDatabase, "is_odoo", value=True),
            self.patch(self.odev.store.databases, "get", None),
            self.patch(self.odev.store.databases, "set") as patched_set,
        ):
            database = LocalDatabase("test-cost")

        patched_set.assert_called_once_with(database)
        self.assertFalse(database._whitelisted)

    def test_03_directory_size_counts_files_at_any_depth(self):
        """The size of a filestore is the sum of its files, wherever they are in it."""
        with TemporaryDirectory() as temporary_directory:
            filestore = Path(temporary_directory)
            (filestore / "ab").mkdir()
            (filestore / "cd" / "nested").mkdir(parents=True)
            (filestore / "ab" / "first").write_bytes(b"1" * 10)
            (filestore / "cd" / "second").write_bytes(b"2" * 200)
            (filestore / "cd" / "nested" / "third").write_bytes(b"3" * 3000)
            (filestore / "empty").mkdir()

            self.assertEqual(LocalDatabase._directory_size(filestore), 3210)

    def test_04_missing_directory_has_no_size(self):
        """A database without a filestore should report an empty one rather than fail."""
        with TemporaryDirectory() as temporary_directory:
            self.assertEqual(LocalDatabase._directory_size(Path(temporary_directory) / "missing"), 0)

    def test_05_delete_reads_the_venv_before_removing_anything(self):
        """Deleting a database should know its virtual environment before dropping what tells which one it is."""
        steps: list[str] = []

        def record(step: str, result: object = None):
            return lambda *_: steps.append(step) or result

        database = MagicMock()
        type(database).venv = PropertyMock(side_effect=record("venv", MagicMock()))
        database.drop.side_effect = record("drop")

        command = DeleteCommand.__new__(DeleteCommand)
        command.args = Namespace(keep=[])

        with (
            self.patch(command, "remove_filestore", side_effect=record("filestore")),
            self.patch(command, "remove_configuration", side_effect=record("configuration")),
            self.patch(command, "remove_venv", side_effect=record("remove_venv")),
        ):
            command.delete_one(database)

        self.assertEqual(steps, ["venv", "filestore", "configuration", "drop", "remove_venv"])
