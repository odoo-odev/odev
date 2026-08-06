from pathlib import Path
from unittest.mock import MagicMock

from odev.common.databases import LocalDatabase
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
