import shutil
from pathlib import Path

from odev.common.plugins import forget_plugins, installed_plugins

from tests.fixtures import OdevTestCase


class TestCommonPlugins(OdevTestCase):
    """Discovery of the plugins installed under the plugins directory."""

    def setUp(self):
        super().setUp()
        self.plugins_path = self.run_path / "discovery-plugins"
        self.plugins_path.mkdir(parents=True, exist_ok=True)
        self.plugin_repository = self.res_path / "repositories" / "test" / "test-plugin"
        self.addCleanup(shutil.rmtree, self.plugins_path, ignore_errors=True)
        # The discovery is cached process-wide, so a test must never leave its own directory behind in it.
        self.addCleanup(forget_plugins)
        forget_plugins()

    def test_01_reads_the_directory_once_while_it_is_untouched(self):
        """Reading the plugins directory again without it changing should hand back the very same result.

        Discovery is what the configuration, the framework and the plugin command all go through, so it has to
        read the filesystem once per run, and report a plugin it had to skip once rather than once per caller.
        """
        self.__link("test_plugin")

        discovery = installed_plugins(self.plugins_path)

        self.assertEqual([plugin.name for plugin in discovery.loaded], ["test/test-plugin"])
        self.assertIs(installed_plugins(self.plugins_path), discovery)

    def test_02_follows_a_link_added_outside_odev(self):
        """A link appearing in the plugins directory should be picked up without anyone clearing the cache.

        The link is the only record that a plugin is installed, so nothing may keep a stale reading of it alive:
        caching it on anything but the state of the directory itself makes odev miss a plugin that is there.
        """
        self.assertEqual(installed_plugins(self.plugins_path).loaded, [])

        self.__link("test_plugin")

        # No forget_plugins() here on purpose: changing the directory has to be enough on its own.
        self.assertEqual(
            [plugin.name for plugin in installed_plugins(self.plugins_path).loaded],
            ["test/test-plugin"],
        )

    def test_03_follows_a_link_removed_outside_odev(self):
        """A link disappearing from the plugins directory should be picked up just the same."""
        link = self.__link("test_plugin")
        self.assertEqual(len(installed_plugins(self.plugins_path).loaded), 1)

        link.unlink()

        self.assertEqual(installed_plugins(self.plugins_path).loaded, [])

    def test_04_reports_a_broken_plugin_once(self):
        """A link that cannot be loaded should be reported, and reported only once for the whole run."""
        self.__link("broken_plugin", target=self.res_path / "repositories" / "test" / "test-addons")

        with self.patch("odev.common.plugins.logger", "warning") as logger_warning:
            discovery = installed_plugins(self.plugins_path)
            installed_plugins(self.plugins_path)

        self.assertEqual(discovery.loaded, [])
        self.assertEqual([plugin.name for plugin in discovery.skipped], ["test/test-addons"])
        self.assertIn("__manifest__.py", discovery.skipped[0].reason)
        logger_warning.assert_called_once()

    def test_04_follows_a_repository_disappearing_under_a_link(self):
        """A plugin whose repository is gone should stop being loaded, without the directory itself changing.

        Removing the repository a link points to leaves the plugins directory untouched, so a discovery keyed on
        that directory alone would go on handing out a plugin there is nothing left to import.
        """
        repository = self.run_path / "vanishing-plugin" / "test" / "test-plugin"
        repository.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.plugin_repository / "__manifest__.py", repository / "__manifest__.py")
        self.__link("test_plugin", target=repository)

        self.assertEqual([plugin.name for plugin in installed_plugins(self.plugins_path).loaded], ["test/test-plugin"])

        shutil.rmtree(repository.parents[1], ignore_errors=True)

        # No forget_plugins() here on purpose: what a link points to is part of what was discovered.
        self.assertEqual(installed_plugins(self.plugins_path).loaded, [])

    def test_04_follows_a_manifest_changing_under_a_link(self):
        """A plugin whose manifest changed, as a pull does, should be read again rather than served from before."""
        repository = self.run_path / "updated-plugin" / "test" / "test-plugin"
        repository.mkdir(parents=True, exist_ok=True)
        manifest = repository / "__manifest__.py"
        manifest.write_text('"""A plugin."""\n\n__version__ = "1.0.0"\n')
        self.__link("test_plugin", target=repository)
        self.addCleanup(shutil.rmtree, repository.parents[1], ignore_errors=True)

        self.assertEqual(installed_plugins(self.plugins_path).loaded[0].manifest["version"], "1.0.0")

        manifest.write_text('"""A plugin."""\n\n__version__ = "2.0.0"\n')

        self.assertEqual(installed_plugins(self.plugins_path).loaded[0].manifest["version"], "2.0.0")

    def test_05_framework_follows_the_directory(self):
        """`Odev.plugins` should reflect the plugins directory, never a reading cached alongside it.

        The framework used to keep its own copy of the discovery, which nothing invalidated when a link changed,
        so odev could go on loading a plugin that had been deleted under it.
        """
        link = self.run_path / "plugins" / "test_plugin"
        self.addCleanup(link.unlink, missing_ok=True)
        link.parent.mkdir(parents=True, exist_ok=True)

        self.assertNotIn("test/test-plugin", [plugin.name for plugin in self.odev.plugins])

        link.symlink_to(self.plugin_repository, target_is_directory=True)

        # No _forget_plugins() here on purpose: the framework must not outlive the state it read.
        self.assertIn("test/test-plugin", [plugin.name for plugin in self.odev.plugins])

        link.unlink()

        self.assertNotIn("test/test-plugin", [plugin.name for plugin in self.odev.plugins])

    def __link(self, name: str, target: Path | None = None) -> Path:
        """Install a plugin the only way there is: by linking it under the plugins directory.

        :param name: Name of the module the plugin is linked as.
        :param target: Repository to link to, the test plugin by default.
        :return: The path to the link.
        """
        link = self.plugins_path / name
        link.symlink_to(target or self.plugin_repository, target_is_directory=True)
        return link
