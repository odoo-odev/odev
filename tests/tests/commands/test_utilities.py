import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odev._version import __version__
from odev.common.odev import plugin_module_name
from odev.common.python import PythonEnv

from tests.fixtures import OdevCommandTestCase


POSTGRES_PATH = "odev.common.connectors.PostgresConnector"
GIT_PATH = "odev.common.connectors.git.GitConnector"
GITHUB_PATH = "odev.common.connectors.git.GithubConnector"


class TestCommandUtilities(OdevCommandTestCase):
    def test_version_01_no_argument(self):
        """Command `odev version` should print the version of the application and stay silent when there is
        nothing new to pull.
        """
        with self.patch(self.odev, "update_available", return_value=False):
            stdout, stderr = self.dispatch_command("version")

        self.assertIn(f"{self.odev.name.capitalize()} version {__version__}", stdout)
        self.assertNotIn("A newer version is available", stderr)

    def test_version_02_update_available(self):
        """Command `odev version` should warn about a newer version only when the repository has incoming
        changes.
        """
        with self.patch(self.odev, "update_available", return_value=True):
            _, stderr = self.dispatch_command("version")

        self.assertIn("A newer version is available", stderr)

    def test_config_01_no_argument(self):
        """Run the command without arguments."""
        stdout, _ = self.dispatch_command("config")
        self.assertIn(" mode ", stdout)
        self.assertIn(" date ", stdout)
        self.assertIn(" version ", stdout)
        self.assertIn(" interval ", stdout)
        self.assertIn(" dumps ", stdout)
        self.assertIn(" repositories ", stdout)

    def test_config_02_print_section(self):
        """Run the command with a specific section and no key."""
        stdout, _ = self.dispatch_command("config", "paths")
        self.assertNotIn(" mode ", stdout)
        self.assertNotIn(" date ", stdout)
        self.assertNotIn(" version ", stdout)
        self.assertNotIn(" interval ", stdout)
        self.assertIn(" dumps ", stdout)
        self.assertIn(" repositories ", stdout)

    def test_config_03_print_key(self):
        """Run the command with a specific section and key."""
        stdout, _ = self.dispatch_command("config", "update.mode")
        self.assertIn(" mode ", stdout)
        self.assertNotIn(" date ", stdout)
        self.assertNotIn(" version ", stdout)
        self.assertNotIn(" interval ", stdout)
        self.assertNotIn(" dumps ", stdout)
        self.assertNotIn(" repositories ", stdout)
        self.assertRegex(stdout, rf"mode\s+{self.odev.config.update.mode}")

    def test_config_04_invalid_key(self):
        """Run the command with an invalid section and key combination."""
        _, stderr = self.dispatch_command("config", "invalid.test")
        self.assertIn(f"'invalid' is not a valid section in config {self.odev.config.name!r}", stderr)

    def test_config_05_set_value(self):
        """Run the command with a section and key combination, set a value."""
        new_update_mode = "always"
        stdout, _ = self.dispatch_command("config", "update.mode", new_update_mode)
        self.assertIn(" mode ", stdout)
        self.assertEqual(self.odev.config.update.mode, new_update_mode)

    def test_config_06_set_invalid_value(self):
        """Run the command with a section and no key."""
        _, stderr = self.dispatch_command("config", "update", "invalid")
        self.assertIn("You must specify a key to set a value", stderr)

    def test_help_01_no_argument(self):
        """Run the command without arguments, display all available commands."""
        stdout, _ = self.dispatch_command("help")
        self.assertIn("The following commands are provided:", stdout)

    def test_help_02_command(self):
        """Run the command with a command argument, display detailed help for a specific command."""
        stdout, _ = self.dispatch_command("help", "version")
        self.assertIn(self.odev.commands["version"]._help, stdout)

    def test_help_03_invalid_command(self):
        """Run the command with an invalid command argument, print an error message."""
        _, stderr = self.dispatch_command("help", "invalid")
        self.assertIn("Cannot display help for inexistent command 'invalid'", stderr)

    def test_help_04_names_only(self):
        """Run the command with the `--names-only` flag, display only the names of the available commands."""
        stdout, _ = self.dispatch_command("help", "--names-only")
        self.assertNotIn("The following commands are provided:", stdout)

        for command in {c._name for c in self.odev.commands.values()}:
            self.assertIn(f"{command}\n", stdout)

    def test_history_01_clear(self):
        """Run the command with the `--clear` flag."""
        with self.patch(self.odev.store.history, "clear") as patched_clear:
            stdout, _ = self.dispatch_command("history", "--clear")

        self.assertIn("Clearing history", stdout)
        patched_clear.assert_called_once_with()

    def test_history_02_no_argument(self):
        """Run the command without arguments, print th history of commands without filter."""
        stdout, _ = self.dispatch_command("history")
        self.assertRegex(stdout, r"ID\s+Command\s+Date")
        self.assertGreater(len(stdout.splitlines()), 4, "there should be at least one line in the history")

    def test_history_03_filter_command(self):
        """Run the command with a command argument, print the history of a specific command."""
        stdout, _ = self.dispatch_command("history", "--command", "history")
        self.assertIn(" history --clear ", stdout)

    def test_history_04_no_history(self):
        """Run the command when there is no history, print an error message."""
        self.odev.store.history.clear()
        _, stderr = self.dispatch_command("history")
        self.assertIn("No history available for all commands", stderr)

    def test_list_01_list_all(self):
        """Run the command, list all existing databases."""
        stdout, _ = self.dispatch_command("list", "--all")
        self.assertRegex(stdout, r"^Listing databases")
        self.assertGreater(len(stdout.splitlines()), 7, "there should be at least 1 lines in the list")

    def test_list_02_names_only(self):
        """Run the command with the `--names-only` flag, display only the names of the databases."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            stdout, _ = self.dispatch_command("list", "--all", "--names-only")

        self.assertRegex(stdout, r"^Listing databases")
        self.assertIn("test1\ntest2\n", stdout)

    def test_list_03_no_result(self):
        """Run the command when there are no databases, print an error message."""
        with self.patch(POSTGRES_PATH, "query", []):
            _, stderr = self.dispatch_command("list")

        self.assertIn("No database found", stderr)

    def test_list_04_expression(self):
        """Run the command with the `--expression` flag, filter the databases."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            stdout, _ = self.dispatch_command("list", "--expression", "test1", "--names-only", "--all")

        self.assertIn("test1\n", stdout)
        self.assertNotIn("test2\n", stdout)

    def test_list_05_expression_no_result(self):
        """Run the command with the `--expression` flag, filter the databases, display an error if no result."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            _, stderr = self.dispatch_command("list", "--expression", "test3")

        self.assertIn("No database found matching pattern 'test3'", stderr)

    def test_setup_cmd_01_no_argument(self):
        """Run the command without arguments, run all scripts."""
        stdout, _ = self.dispatch_command("setup")
        self.assertEqual("Hello, odev from script 1!\nHello, odev from script 2!\n", stdout)

    def test_setup_cmd_02_script(self):
        """Run the command with an argument, run only the selected script."""
        stdout, _ = self.dispatch_command("setup", "setup_script_1")
        self.assertEqual("Hello, odev from script 1!\n", stdout)

    def test_update_01_no_argument(self):
        """Run the command without arguments, update the application."""
        self.odev.config.update.date = "1995-12-21 00:00:00"
        self.odev.config.update.interval = 1
        self.odev.config.update.mode = "always"
        self.odev.config.update.version = "3.0.0"

        def upgrade():
            self.odev.config.update.version = __version__

        with (
            self.patch_property(type(self.odev), "version", "3.0.0"),
            self.patch(self.odev, "upgrade", side_effect=upgrade),
        ):
            stdout, _ = self.dispatch_command("update")

        self.assertEqual(self.odev.config.update.version, __version__)
        self.assertIn("Current version: 3.0.0", stdout)
        self.assertIn(f"Updated to {__version__}!", stdout)

    def test_plugin_01_single(self):
        """Run the command to enable or disable a plugin."""
        plugin = "test/test-plugin"
        plugin_link = Path(self.odev.plugins_path) / "test_plugin"
        self.odev.config.paths.repositories = self.res_path / "repositories"

        # Sanity check
        if plugin_link.is_symlink():
            plugin_link.unlink()

        with (
            self.patch_property(GIT_PATH, "exists", value=True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", plugin)

        self.assertIn(plugin, self.odev.config.plugins.enabled)
        self.assertTrue(plugin_link.is_symlink())

        stdout, _ = self.dispatch_command("plugin", "--enable", plugin)
        self.assertIn(f"Plugin '{plugin}' is already installed", stdout)
        self.assertTrue(self.odev._plugin_is_installed(plugin))

        with self.patch(self.odev.console, "confirm", return_value=True):
            self.dispatch_command("plugin", "--disable", plugin)

        self.assertNotIn(plugin, self.odev.config.plugins.enabled)
        self.assertFalse(plugin_link.is_symlink())

        with self.patch(self.odev.console, "confirm", return_value=True):
            stdout, _ = self.dispatch_command("plugin", "--disable", plugin)

        self.assertIn(f"Plugin '{plugin}' is not installed", stdout)
        self.assertFalse(self.odev._plugin_is_installed(plugin))

    def test_plugin_02_enable_invalid(self):
        """Run the command with an invalid plugin to enable."""
        plugin = "odoo-odev/invalid"
        _, stderr = self.dispatch_command("plugin", "--enable", plugin)
        self.assertIn(f"Failed to clone repository '{plugin}'", stderr)
        self.assertFalse(self.odev._plugin_is_installed(plugin))

    def test_plugin_03_enable_dependencies(self):
        """Run the command to enable a plugin with dependencies."""
        plugin = "test/test-plugin"
        dependent = "test/test-plugin-dep"
        self.odev.config.paths.repositories = self.res_path / "repositories"

        with (
            self.patch_property(GIT_PATH, "exists", value=True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", dependent)

        self.assertTrue(self.odev._plugin_is_installed(dependent))
        self.assertTrue(self.odev._plugin_is_installed(plugin))

        with self.patch(self.odev.console, "confirm", return_value=True):
            stdout, _ = self.dispatch_command("plugin", "--disable", plugin)

        self.assertIn(f"Uninstalling plugin {plugin!r} will also uninstall the following dependent plugins", stdout)
        self.assertFalse(self.odev._plugin_is_installed(plugin))
        self.assertFalse(self.odev._plugin_is_installed(dependent))

    def test_plugin_04_list(self):
        """Run the command to list plugins, showing enabled and downloaded ones alike."""
        self.__enable_test_plugin()
        stdout, _ = self.__dispatch_plugin("--list")

        self.assertRegex(stdout, r"Plugin\s+Version\s+Branch\s+State\s+Depends")
        self.assertRegex(stdout, r"test/test-plugin\s+1\.0\.0\s+enabled")
        self.assertRegex(stdout, r"test/test-plugin-dep\s+1\.0\.0\s+disabled\s+test-plugin")
        self.assertNotIn("test/test-addons", stdout)

    def test_plugin_05_list_shadowed(self):
        """Run the command to list plugins when two enabled plugins share the same module name."""
        self.__enable_test_plugin()
        self.odev.config.plugins.enabled = [*self.odev.config.plugins.enabled, "other/test-plugin"]

        stdout, _ = self.__dispatch_plugin("--list")

        self.assertRegex(stdout, r"test/test-plugin\s+1\.0\.0\s+enabled")
        self.assertRegex(stdout, r"other/test-plugin\s+shadowed")
        self.assertIn("other/test-plugin (shadowed by test/test-plugin)", stdout)

    def test_plugin_06_search(self):
        """Run the command to search plugins on GitHub, keeping only valid plugin repositories."""
        self.odev.config.paths.repositories = self.res_path / "repositories"
        manifest = (self.res_path / "repositories" / "test" / "test-plugin" / "__manifest__.py").read_text()
        repositories = [
            self.__github_repository("test/archived-plugin", archived=True),
            self.__github_repository("odoo-odev/odev-plugin-template"),
            self.__github_repository("test/test-plugin", stars=3),
            self.__github_repository("other/remote-plugin"),
            self.__github_repository("other/not-a-plugin", description="Not a plugin at all"),
        ]

        with (
            self.patch(GITHUB_PATH, "search_repositories", return_value=repositories) as search,
            self.patch(GITHUB_PATH, "get_repository_file", side_effect=[manifest, manifest, None]),
        ):
            stdout, _ = self.__dispatch_plugin("--search")

        self.assertRegex(stdout, r"Plugin\s+Version\s+Stars\s+State\s+Description")
        self.assertRegex(stdout, r"test/test-plugin\s+1\.0\.0\s+3\s+disabled")
        self.assertRegex(stdout, r"other/remote-plugin\s+1\.0\.0\s+0\s+not downloaded")
        self.assertNotIn("other/not-a-plugin", stdout)
        self.assertNotIn("test/archived-plugin", stdout)
        self.assertNotIn("odev-plugin-template", stdout)
        self.assertTrue(search.call_args.args[0].startswith("odev plugin"))

    def test_plugin_07_search_terms(self):
        """Run the command to search plugins with additional terms, showing the state of enabled plugins."""
        self.__enable_test_plugin()
        manifest = (self.res_path / "repositories" / "test" / "test-plugin" / "__manifest__.py").read_text()

        with (
            self.patch(
                GITHUB_PATH,
                "search_repositories",
                return_value=[self.__github_repository("test/test-plugin")],
            ) as search,
            self.patch(GITHUB_PATH, "get_repository_file", return_value=manifest),
        ):
            stdout, _ = self.__dispatch_plugin("--search", "editor")

        self.assertRegex(stdout, r"test/test-plugin\s+1\.0\.0\s+0\s+enabled")
        self.assertIn("editor", search.call_args.args[0])

    def test_plugin_08_search_no_result(self):
        """Run the command to search plugins when no repository exposes a valid manifest."""
        self.odev.config.paths.repositories = self.res_path / "repositories"

        with (
            self.patch(
                GITHUB_PATH,
                "search_repositories",
                return_value=[self.__github_repository("other/not-a-plugin")],
            ),
            self.patch(GITHUB_PATH, "get_repository_file", return_value=None),
        ):
            _, stderr = self.dispatch_command("plugin", "--search", "unknown")

        self.assertIn("No odev plugin found matching 'unknown'", stderr)

    def test_plugin_09_show_qualified_name(self):
        """Run the command to show a plugin using its fully qualified name."""
        self.__enable_test_plugin()

        stdout, _ = self.dispatch_command("plugin", "--show", "test/test-plugin")
        self.assertIn("Plugin 'test/test-plugin' is enabled", stdout)

        stdout, _ = self.dispatch_command("plugin", "--show", "test-plugin")
        self.assertIn("Plugin 'test/test-plugin' is enabled", stdout)

    def test_plugin_10_show_downloaded(self):
        """Run the command to show a plugin available locally but not enabled, without querying GitHub."""
        self.__enable_test_plugin()

        with self.patch(GITHUB_PATH, "get_repository", return_value=None) as get_repository:
            stdout, _ = self.__dispatch_plugin("--show", "test/test-plugin-dep")

        self.assertIn("Plugin 'test/test-plugin-dep' is disabled", stdout)
        self.assertRegex(stdout, r"Version:\s+1\.0\.0")
        self.assertRegex(stdout, r"Depends:\s+test/test-plugin")
        self.assertRegex(stdout, r"Path:\s+.*test-plugin-dep")
        self.assertRegex(stdout, r"URL:\s+https://github\.com/test/test-plugin-dep")
        get_repository.assert_not_called()

    def test_plugin_11_show_not_downloaded(self):
        """Run the command to show a plugin that is not available locally, fetching its manifest from GitHub."""
        self.odev.config.paths.repositories = self.res_path / "repositories"
        manifest = (self.res_path / "repositories" / "test" / "test-plugin" / "__manifest__.py").read_text()

        with (
            self.patch(
                GITHUB_PATH,
                "get_repository",
                return_value=self.__github_repository("other/remote-plugin", stars=42),
            ) as get_repository,
            self.patch(GITHUB_PATH, "get_repository_file", return_value=manifest) as get_repository_file,
        ):
            stdout, _ = self.__dispatch_plugin("--show", "other/remote-plugin")

        self.assertIn("Plugin 'other/remote-plugin' is not downloaded", stdout)
        self.assertRegex(stdout, r"Version:\s+1\.0\.0")
        self.assertRegex(stdout, r"Branch:\s+main")
        self.assertRegex(stdout, r"Stars:\s+42")
        self.assertNotIn("Path:", stdout)
        self.assertIn("Run 'odev plugin --enable other/remote-plugin' to install this plugin", stdout)
        get_repository.assert_called_once_with("other/remote-plugin")
        self.assertEqual(get_repository_file.call_args.args[1], "__manifest__.py")

    def test_plugin_12_show_archived_and_excluded(self):
        """Run the command to show plugins that can be found on GitHub but should not be installed."""
        self.odev.config.paths.repositories = self.res_path / "repositories"
        manifest = (self.res_path / "repositories" / "test" / "test-plugin" / "__manifest__.py").read_text()

        with (
            self.patch(
                GITHUB_PATH,
                "get_repository",
                return_value=self.__github_repository("other/archived-plugin", archived=True),
            ),
            self.patch(GITHUB_PATH, "get_repository_file", return_value=manifest),
        ):
            stdout, _ = self.__dispatch_plugin("--show", "other/archived-plugin")

        self.assertIn("Repository 'other/archived-plugin' is archived", stdout)

        with (
            self.patch(
                GITHUB_PATH,
                "get_repository",
                return_value=self.__github_repository("odoo-odev/odev-plugin-template"),
            ),
            self.patch(GITHUB_PATH, "get_repository_file", return_value=manifest),
        ):
            stdout, _ = self.__dispatch_plugin("--show", "odoo-odev/odev-plugin-template")

        self.assertIn("is a template used to create new plugins and cannot be installed", stdout)
        self.assertNotIn("--enable odoo-odev/odev-plugin-template", stdout)

    def test_plugin_13_show_unknown(self):
        """Run the command to show a plugin that is neither available locally nor on GitHub."""
        self.odev.config.paths.repositories = self.res_path / "repositories"

        with self.patch(GITHUB_PATH, "get_repository", return_value=None):
            stdout, _ = self.__dispatch_plugin("--show", "other/unknown-plugin")

        self.assertIn("Plugin 'other/unknown-plugin' is not downloaded", stdout)
        self.assertNotIn("Version:", stdout)

        with self.patch(GITHUB_PATH, "get_repository", return_value=None) as get_repository:
            stdout, _ = self.__dispatch_plugin("--show", "unknown-plugin")

        self.assertIn("Plugin 'unknown-plugin' is not downloaded", stdout)
        self.assertIn("Use the full name of the plugin", stdout)
        get_repository.assert_not_called()

    def test_plugin_14_show_all(self):
        """Run the command to show all plugins available locally, enabled or not."""
        self.__enable_test_plugin()

        with self.patch(GITHUB_PATH, "get_repository", return_value=None) as get_repository:
            stdout, _ = self.__dispatch_plugin("--show")

        self.assertIn("Plugin 'test/test-plugin' is enabled", stdout)
        self.assertIn("Plugin 'test/test-plugin-dep' is disabled", stdout)
        get_repository.assert_not_called()

    def test_plugin_15_purge(self):
        """Run the command to purge a plugin, removing its link, its configuration entry and its clone."""
        plugin = "test/test-plugin"
        repositories_path = self.__sandbox_repositories()
        plugin_link = Path(self.odev.plugins_path) / "test_plugin"
        self.addCleanup(plugin_link.unlink, missing_ok=True)

        with (
            self.patch_property(GIT_PATH, "exists", value=True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", plugin)

        self.assertTrue(plugin_link.is_symlink())

        with self.patch(self.odev.console, "confirm", return_value=True):
            stdout, _ = self.dispatch_command("plugin", "--purge", "test-plugin")

        self.assertIn(f"Purged plugin {plugin!r}", stdout)
        self.assertNotIn(plugin, self.odev.config.plugins.enabled)
        self.assertFalse(plugin_link.is_symlink())
        self.assertFalse((repositories_path / plugin).exists())

    def test_plugin_16_purge_aborted(self):
        """Run the command to purge a plugin and refuse the confirmation, leaving the clone untouched."""
        plugin = "test/test-plugin"
        repositories_path = self.__sandbox_repositories()

        with self.patch(self.odev.console, "confirm", return_value=False):
            _, stderr = self.dispatch_command("plugin", "--purge", plugin)

        self.assertIn("Aborting plugin purge", stderr)
        self.assertTrue((repositories_path / plugin).is_dir())

    def test_plugin_17_purge_dependents(self):
        """Run the command to purge a plugin, purging the plugins depending on it as well."""
        plugin = "test/test-plugin"
        dependent = "test/test-plugin-dep"
        repositories_path = self.__sandbox_repositories()

        with (
            self.patch_property(GIT_PATH, "exists", value=True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", dependent)

        for name in (plugin, dependent):
            self.addCleanup(Path(self.odev.plugins_path / plugin_module_name(name)).unlink, missing_ok=True)

        self.assertTrue(self.odev._plugin_is_installed(dependent))

        with self.patch(self.odev.console, "confirm", return_value=True):
            stdout, stderr = self.dispatch_command("plugin", "--purge", plugin)

        self.assertIn(f"Purging plugin {plugin!r} will also purge the following dependent plugins", stderr)
        self.assertIn(dependent, stderr)
        self.assertIn(f"Purged plugin {dependent!r}", stdout)

        for name in (plugin, dependent):
            self.assertNotIn(name, self.odev.config.plugins.enabled)
            self.assertFalse((repositories_path / name).exists())
            self.assertFalse((self.odev.plugins_path / plugin_module_name(name)).is_symlink())

    def test_plugin_18_purge_broken_manifest(self):
        """Run the command to purge a plugin whose own manifest is broken, still finding its dependents."""
        plugin = "test/test-plugin"
        dependent = "test/test-plugin-dep"
        repositories_path = self.__sandbox_repositories()
        (repositories_path / plugin / "__manifest__.py").write_text("this is not valid python(")

        with self.patch(self.odev.console, "confirm", return_value=True):
            self.dispatch_command("plugin", "--purge", plugin)

        self.assertFalse((repositories_path / plugin).exists())
        self.assertFalse((repositories_path / dependent).exists())

    def test_plugin_19_purge_forced(self):
        """Run the command to purge a plugin with `--force`, bypassing the confirmation prompt."""
        plugin = "test/test-plugin"
        repositories_path = self.__sandbox_repositories()

        stdout, _ = self.dispatch_command("plugin", "--purge", "--force", plugin)

        self.assertIn(f"Purged plugin {plugin!r}", stdout)
        self.assertFalse((repositories_path / plugin).exists())

    def test_plugin_20_purge_unknown(self):
        """Run the command to purge a plugin by repository name only when no such clone exists locally."""
        self.__sandbox_repositories()
        _, stderr = self.dispatch_command("plugin", "--purge", "unknown-plugin")
        self.assertIn("No plugin named 'unknown-plugin' found locally", stderr)

    def __sandbox_repositories(self) -> Path:
        """Copy the plugin test resources to a throwaway repositories directory, safe to delete from."""
        repositories_path = self.run_path / "repositories"
        shutil.rmtree(repositories_path, ignore_errors=True)
        shutil.copytree(self.res_path / "repositories", repositories_path)
        self.addCleanup(shutil.rmtree, repositories_path, ignore_errors=True)
        self.odev.config.paths.repositories = repositories_path
        return repositories_path

    def __dispatch_plugin(self, *arguments: str) -> tuple[str, str]:
        """Run the plugin command on a wide terminal so table columns are not cropped."""
        with patch.dict(os.environ, {"COLUMNS": "200"}):
            return self.dispatch_command("plugin", *arguments)

    def __enable_test_plugin(self):
        """Enable the test plugin from the local test resources and unlink it after the test."""
        self.odev.config.paths.repositories = self.res_path / "repositories"
        plugin_link = Path(self.odev.plugins_path) / "test_plugin"
        self.addCleanup(plugin_link.unlink, missing_ok=True)

        with (
            self.patch_property(GIT_PATH, "exists", value=True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", "test/test-plugin")

    def __github_repository(self, full_name: str, description: str = "", stars: int = 0, archived: bool = False):
        """Build a stand-in for a repository as returned by the GitHub API."""
        return SimpleNamespace(
            full_name=full_name,
            html_url=f"https://github.com/{full_name}",
            description=description,
            stargazers_count=stars,
            archived=archived,
            default_branch="main",
        )


class TestCommandUtilitiesVenv(OdevCommandTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.venv = PythonEnv(cls.odev.venvs_path / "test")
        cls.venv.create()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.run_path.as_posix(), ignore_errors=True)
        super().tearDownClass()

    def test_01_invalid_name(self):
        """Run the command with an invalid virtual environment name."""
        _, stderr = self.dispatch_command("venv", "invalid", "--command", "print('test')")
        self.assertRegex(stderr, r"Virtual environment 'invalid' does not exist")

    def test_02_python_command(self):
        """Run the command with a name valid argument and a python command."""
        stdout, _ = self.dispatch_command("venv", self.venv.path.as_posix(), "--command", "print('test')")
        self.assertRegex(
            stdout, r"python[\d.?]*\s-c\s[\\'\"]+print[\\'\"\(]+test[\\'\"\)]+ in virtual environment \'test\'"
        )

    def test_03_pip_command(self):
        """Run the command with a pip command."""
        stdout, _ = self.dispatch_command("venv", self.venv.path.as_posix(), "--command", "pip --version")
        self.assertRegex(stdout, r"python[\d.?]*\s-m\spip\s--version\' in virtual environment \'test\'")
