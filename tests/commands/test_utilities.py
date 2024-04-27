from pathlib import Path

from odev._version import __version__

from tests.fixtures import OdevCommandTestCase


POSTGRES_PATH = "odev.common.connectors.PostgresConnector"
GIT_PATH = "odev.common.connectors.git.GitConnector"


class TestCommandUtilitiesVersion(OdevCommandTestCase):
    """Command `odev version` should print the version of the application."""

    def test_01_no_argument(self):
        """Command `odev version` should print the version of the application."""
        stdout, _ = self.dispatch_command("version")
        self.assertIn(f"Odev-test version {__version__}", stdout)


class TestCommandUtilitiesConfig(OdevCommandTestCase):
    """Command `odev config` should print the configuration of the application or allow setting new values."""

    def test_01_no_argument(self):
        """Run the command without arguments."""
        stdout, _ = self.dispatch_command("config")
        self.assertIn(" mode ", stdout)
        self.assertIn(" date ", stdout)
        self.assertIn(" version ", stdout)
        self.assertIn(" interval ", stdout)
        self.assertIn(" dumps ", stdout)
        self.assertIn(" repositories ", stdout)

    def test_02_print_section(self):
        """Run the command with a specific section and no key."""
        stdout, _ = self.dispatch_command("config", "paths")
        self.assertNotIn(" mode ", stdout)
        self.assertNotIn(" date ", stdout)
        self.assertNotIn(" version ", stdout)
        self.assertNotIn(" interval ", stdout)
        self.assertIn(" dumps ", stdout)
        self.assertIn(" repositories ", stdout)

    def test_03_print_key(self):
        """Run the command with a specific section and key."""
        stdout, _ = self.dispatch_command("config", "update.mode")
        self.assertIn(" mode ", stdout)
        self.assertNotIn(" date ", stdout)
        self.assertNotIn(" version ", stdout)
        self.assertNotIn(" interval ", stdout)
        self.assertNotIn(" dumps ", stdout)
        self.assertNotIn(" repositories ", stdout)
        self.assertRegex(stdout, rf"mode\s+{self.odev.config.update.mode}")

    def test_04_invalid_key(self):
        """Run the command with an invalid section and key combination."""
        _, stderr = self.dispatch_command("config", "invalid.test")
        self.assertIn(f"'invalid' is not a valid section in config {self.odev.config.name!r}", stderr)

    def test_05_set_value(self):
        """Run the command with a section and key combination, set a value."""
        new_update_mode = "always"
        stdout, _ = self.dispatch_command("config", "update.mode", new_update_mode)
        self.assertIn(" mode ", stdout)
        self.assertEqual(self.odev.config.update.mode, new_update_mode)

    def test_06_set_invalid_value(self):
        """Run the command with a section and no key."""
        _, stderr = self.dispatch_command("config", "update", "invalid")
        self.assertIn("You must specify a key to set a value", stderr)


class TestCommandUtilitiesHelp(OdevCommandTestCase):
    """Command `odev help` should print the help message of the application or the detailed description of a command."""

    def test_01_no_argument(self):
        """Run the command without arguments, display all available commands."""
        stdout, _ = self.dispatch_command("help")
        self.assertIn("The following commands are provided:", stdout)

    def test_02_command(self):
        """Run the command with a command argument, display detailed help for a specific command."""
        stdout, _ = self.dispatch_command("help", "version")
        self.assertIn(self.odev.commands["version"]._help, stdout)

    def test_03_invalid_command(self):
        """Run the command with an invalid command argument, print an error message."""
        _, stderr = self.dispatch_command("help", "invalid")
        self.assertIn("Cannot display help for inexistent command 'invalid'", stderr)

    def test_04_names_only(self):
        """Run the command with the `--names-only` flag, display only the names of the available commands."""
        stdout, _ = self.dispatch_command("help", "--names-only")
        self.assertNotIn("The following commands are provided:", stdout)
        
        for command in {c._name for c in self.odev.commands.values()}:
            self.assertIn(f"{command}\n", stdout)


class TestCommandUtilitiesHistory(OdevCommandTestCase):
    """Command `odev history` should print the history of the application or allow clearing it."""

    def test_01_clear(self):
        """Run the command with the `--clear` flag."""
        with self.patch(self.odev.store.history, "clear") as patched_clear:
            stdout, _ = self.dispatch_command("history", "--clear")

        self.assertIn("Clearing history", stdout)
        patched_clear.assert_called_once_with()

    def test_02_no_argument(self):
        """Run the command without arguments, print th history of commands without filter."""
        stdout, _ = self.dispatch_command("history")
        self.assertRegex(stdout, r"ID\s+Command\s+Date")
        self.assertGreater(len(stdout.splitlines()), 4, "there should be at least one line in the history")

    def test_03_filter_command(self):
        """Run the command with a command argument, print the history of a specific command."""
        stdout, _ = self.dispatch_command("history", "--command", "history")
        self.assertIn(" history --clear ", stdout)

    def test_04_no_history(self):
        """Run the command when there is no history, print an error message."""
        self.odev.store.history.clear()
        _, stderr = self.dispatch_command("history")
        self.assertIn("No history available for all commands", stderr)


class TestCommandUtilitiesList(OdevCommandTestCase):
    """Command `odev list` should print the list of local databases."""

    def test_01_list_all(self):
        """Run the command, list all existing databases."""
        stdout, _ = self.dispatch_command("list", "--all")
        self.assertRegex(stdout, r"Name\s+Vers")
        self.assertGreater(len(stdout.splitlines()), 7, "there should be at least 1 lines in the list")

    def test_02_names_only(self):
        """Run the command with the `--names-only` flag, display only the names of the databases."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            stdout, _ = self.dispatch_command("list", "--all", "--names-only")

        self.assertNotRegex(stdout, r"Name\s+Vers")
        self.assertIn("test1\ntest2\n", stdout)

    def test_03_no_result(self):
        """Run the command when there are no databases, print an error message."""
        with self.patch(POSTGRES_PATH, "query", []):
            _, stderr = self.dispatch_command("list")

        self.assertIn("No database found", stderr)

    def test_04_expression(self):
        """Run the command with the `--expression` flag, filter the databases."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            stdout, _ = self.dispatch_command("list", "--expression", "test1", "--names-only", "--all")

        self.assertIn("test1\n", stdout)
        self.assertNotIn("test2\n", stdout)

    def test_05_expression_no_result(self):
        """Run the command with the `--expression` flag, filter the databases, display an error if no result."""
        with self.patch(POSTGRES_PATH, "query", [("test1",), ("test2",)]):
            _, stderr = self.dispatch_command("list", "--expression", "test3")

        self.assertIn("No database found matching pattern 'test3'", stderr)


class TestCommandUtilitiesSetup(OdevCommandTestCase):
    """Command `odev setup` should run the setup scripts."""

    def test_01_no_argument(self):
        """Run the command without arguments, run all scripts."""
        stdout, _ = self.dispatch_command("setup")
        self.assertEqual("Hello, odev from script 1!\nHello, odev from script 2!\n", stdout)

    def test_02_script(self):
        """Run the command with an argument, run only the selected script."""
        stdout, _ = self.dispatch_command("setup", "setup_script_1")
        self.assertEqual("Hello, odev from script 1!\n", stdout)


class TestCommandUtilitiesUpdate(OdevCommandTestCase):
    """Command `odev update` should update the application."""

    def test_01_no_argument(self):
        """Run the command without arguments, update the application."""
        self.odev.config.update.date = "1995-12-21 00:00:00"
        self.odev.config.update.interval = 1
        self.odev.config.update.mode = "always"
        self.odev.config.update.version = "3.0.0"

        def upgrade():
            self.odev.config.update.version = __version__

        with self.patch(self.odev, "upgrade", side_effect=upgrade):
            stdout, _ = self.dispatch_command("update")

        self.assertEqual(self.odev.config.update.version, __version__)
        self.assertIn("Current version: 3.0.0", stdout)
        self.assertIn(f"Updated to {__version__}!", stdout)


class TestCommandUtilitiesPlugin(OdevCommandTestCase):
    """Command `odev plugin` should enable and disable plugins to add new features and commands."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plugin = "test/test-plugin"
        cls.plugin_link = Path(cls.odev.plugins_path) / "test_plugin"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.plugin_link.unlink(missing_ok=True)

    def test_01_enable(self):
        """Run the command to enable a plugin."""
        self.odev.config.paths.repositories = self.odev.tests_path / "resources" / "repositories"

        with (
            self.patch_property(GIT_PATH, "exists", True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--enable", self.plugin)

        self.assertIn(self.plugin, self.odev.config.plugins.enabled)
        self.assertTrue(self.plugin_link.is_symlink())

    def test_02_disable(self):
        """Run the command to disable a plugin."""
        self.odev.config.plugins.enabled = [self.plugin]

        with (
            self.patch_property(GIT_PATH, "exists", True),
            self.patch(GIT_PATH, "update"),
        ):
            self.dispatch_command("plugin", "--disable", self.plugin)

        self.assertNotIn(self.plugin, self.odev.config.plugins.enabled)
        self.assertFalse(self.plugin_link.is_symlink())

    def test_03_enable_already_enabled(self):
        """Run the command to enable an already enabled plugin."""
        self.odev.config.plugins.enabled = [self.plugin]
        _, stderr = self.dispatch_command("plugin", "--enable", self.plugin)
        self.assertIn(f"Plugin '{self.plugin}' is already enabled", stderr)

    def test_04_disable_already_disabled(self):
        """Run the command to disable an already disabled plugin."""
        self.odev.config.plugins.enabled = []
        _, stderr = self.dispatch_command("plugin", "--disable", self.plugin)
        self.assertIn(f"Plugin '{self.plugin}' is not enabled", stderr)

    def test_05_enable_invalid(self):
        """Run the command with an invalid plugin to enable."""
        _, stderr = self.dispatch_command("plugin", "--enable", "invalid/invalid")
        self.assertNotIn("invalid/invalid", self.odev.config.plugins.enabled)
        self.assertIn("Failed to clone repository 'invalid/invalid'", stderr)


class TestCommandUtilitiesVenv(OdevCommandTestCase):
    """Command `odev venv` should interact with virtual environments created and managed by Odev."""

    def test_01_invalid_name(self):
        """Run the command with an invalid virtual environment name."""
        _, stderr = self.dispatch_command("venv", "invalid", "print('test')")
        self.assertRegex(stderr, r"Virtual environment 'invalid' does not exist")

    def test_02_python_command(self):
        """Run the command with a name valid argument and a python command."""
        stdout, _ = self.dispatch_command("venv", self.venv.path.as_posix(), "print('test')")
        self.assertRegex(stdout, r"python[\d.?]*\s-c\s[\\'\"]+print[\\'\"\(]+test[\\'\"\)]+ in virtual environment \'test\'")

    def test_03_pip_command(self):
        """Run the command with a pip command."""
        stdout, _ = self.dispatch_command("venv", self.venv.path.as_posix(), "pip --version")
        self.assertRegex(stdout, r"python[\d.?]*\s-m\spip\s--version\' in virtual environment \'test\'")
