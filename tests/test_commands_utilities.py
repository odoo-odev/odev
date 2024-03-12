from odev._version import __version__
from odev.common.errors import CommandError, ConnectorError
from odev.common.python import PythonEnv
from tests.fixtures import CaptureOutput, OdevCommandTestCase


class TestUtilCommands(OdevCommandTestCase):
    """Test the utility commands of the application."""

    def test_command_config(self):
        """Command `odev config` should print the configuration of the application or allow setting new values."""

        # ----------------------------------------------------------------------
        # Run the command without arguments
        # ----------------------------------------------------------------------

        command = self.setup_command("config")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertIn(" date ", output.stdout)
        self.assertIn(" version ", output.stdout)
        self.assertIn(" interval ", output.stdout)
        self.assertIn(" dumps ", output.stdout)
        self.assertIn(" repositories ", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with a specific section and no key
        # ----------------------------------------------------------------------

        command = self.setup_command("config", "paths")

        with CaptureOutput() as output:
            command.run()

        self.assertNotIn(" mode ", output.stdout)
        self.assertNotIn(" date ", output.stdout)
        self.assertNotIn(" version ", output.stdout)
        self.assertNotIn(" interval ", output.stdout)
        self.assertIn(" dumps ", output.stdout)
        self.assertIn(" repositories ", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with a specific section and key combination
        # ----------------------------------------------------------------------

        command = self.setup_command("config", "update.mode")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertNotIn(" date ", output.stdout)
        self.assertNotIn(" version ", output.stdout)
        self.assertNotIn(" interval ", output.stdout)
        self.assertNotIn(" dumps ", output.stdout)
        self.assertNotIn(" repositories ", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with an invalid section and key combination
        # ----------------------------------------------------------------------

        command = self.setup_command("config", "test")

        with self.assertRaises(CommandError, msg=f"'test' is not a valid section in config {self.odev.config.name!r}"):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command with a section and key combination, set a value
        # ----------------------------------------------------------------------

        self.odev.config.update.mode = "ask"
        command = self.setup_command("config", "update.mode always")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertEqual(self.odev.config.update.mode, "always")

        # ----------------------------------------------------------------------
        # Run the command with a section but no key, set a value
        # ----------------------------------------------------------------------

        self.odev.config.update.mode = "ask"
        command = self.setup_command("config", "update mode")

        with self.assertRaises(CommandError, msg="You must specify a key to set a value"):
            command.run()

    def test_command_help(self):
        """Command `odev help` should print available commands and detailed help about other commands when requested."""

        # ----------------------------------------------------------------------
        # Run the command without arguments
        # ----------------------------------------------------------------------

        command = self.setup_command("help")

        with CaptureOutput() as output:
            command.run()

        self.assertIn("The following commands are provided:", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with a command argument
        # ----------------------------------------------------------------------

        command = self.setup_command("help", "help")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(self.odev.commands["help"]._help, output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with an invalid command argument
        # ----------------------------------------------------------------------

        command = self.setup_command("help", "invalid-command")

        with (
            self.assertRaises(CommandError, msg="Cannot display help for inexistent command 'invalid-command'"),
        ):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command with the --names-only argument
        # ----------------------------------------------------------------------

        command = self.setup_command("help", "--names-only")

        with CaptureOutput() as output:
            command.run()

        self.assertIn("help\n", output.stdout)

    def test_command_history(self):
        """Command `odev history` should print or clear the history of previously run commands."""

        # ----------------------------------------------------------------------
        # Run the command to clear the history
        # ----------------------------------------------------------------------

        command = self.setup_command("history", "--clear")
        command.run()
        self.assertEqual(self.odev.store.history.get(), [], "should clear the history")

        command._argv = ["history", "--clear"]
        self.odev.store.history.set(command)

        # ----------------------------------------------------------------------
        # Run the command without arguments
        # ----------------------------------------------------------------------

        command = self.setup_command("history")

        with CaptureOutput() as output:
            command.run()

        self.assertRegex(output.stdout.splitlines()[1], r"ID\s+Command\s+Date", "should print the history")
        self.assertGreater(len(output.stdout.splitlines()), 4, "there should be at least one line (table omitted) in the history")

        # ----------------------------------------------------------------------
        # Run the command with a filter on the command used
        # ----------------------------------------------------------------------

        command = self.setup_command("history", "--command history")

        with CaptureOutput() as output:
            command.run()

        self.assertRegex("\n".join(output.stdout.splitlines()[3:-1]), r"history --clear", "should print the history")

        # ----------------------------------------------------------------------
        # Raise an error if no history could be found
        # ----------------------------------------------------------------------

        self.odev.store.history.clear()
        command = self.setup_command("history")

        with self.assertRaises(CommandError, msg="No history available for all databases and all commands"):
            command.run()

    def test_command_list(self):
        """Command `odev list` should print the list of databases available in PostgreSQL and details about those."""

        # ----------------------------------------------------------------------
        # Run the command without arguments (list non-odoo databases)
        # ----------------------------------------------------------------------

        command = self.setup_command("list", "--all")

        with CaptureOutput() as output:
            command.run()

        self.assertGreater(len(output.stdout.splitlines()), 4, "there should be at least one line (table omitted) in the list")

        # ----------------------------------------------------------------------
        # Run the command with the --names-only argument
        # ----------------------------------------------------------------------

        command = self.setup_command("list", "--names-only --all")

        with (
            CaptureOutput() as output,
            self.patch(command.connector, "query", return_value=[("test1",), ("test2",)]),
        ):
            command.run()

        self.assertIn("test1\ntest2\n", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with no result
        # ----------------------------------------------------------------------

        command = self.setup_command("list")

        with (
            self.assertRaises(CommandError, msg="No database found"),
            self.patch(command.connector, "query", return_value=[]),
        ):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command with the --expression argument
        # ----------------------------------------------------------------------

        command = self.setup_command("list", "--expression test1 --names-only --all")

        with (
            CaptureOutput() as output,
            self.patch(command.connector, "query", return_value=[("test1",), ("test2",)]),
        ):
            command.run()

        self.assertIn("test1\n", output.stdout)
        self.assertNotIn("test2\n", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with the --expression argument and no result
        # ----------------------------------------------------------------------

        command = self.setup_command("list", "--expression no-match --names-only --all")

        with (
            self.assertRaises(CommandError, msg="No database found matching pattern 'no-match'"),
            self.patch(command.connector, "query", return_value=[("test1",), ("test2",)]),
        ):
            command.run()

    def test_command_plugin(self):
        """Command `odev plugin` should enable and disable plugins to add new features and commands."""

        # ----------------------------------------------------------------------
        # Run the command to enable a plugin
        # ----------------------------------------------------------------------

        command = self.setup_command("plugin", "enable test/test")

        with self.patch(command.odev, "load_plugins"):
            command.run()

        self.assertIn("test/test", self.odev.config.plugins.enabled, "should enable the plugin")

        # ----------------------------------------------------------------------
        # Run the command to enable an already enabled plugin
        # ----------------------------------------------------------------------

        with self.assertRaises(CommandError, msg="Plugin 'test/test' is already enabled"):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command to disable a plugin
        # ----------------------------------------------------------------------

        command = self.setup_command("plugin", "disable test/test")

        with self.patch(command.odev, "load_plugins"):
            command.run()

        self.assertNotIn("test/test", self.odev.config.plugins.enabled, "should disable the plugin")

        # ----------------------------------------------------------------------
        # Run the command to disabled an already disabled plugin
        # ----------------------------------------------------------------------

        with self.assertRaises(CommandError, msg="Plugin 'test/test' is already disabled"):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command with an invalid plugin to enable
        # ----------------------------------------------------------------------

        command = self.setup_command("plugin", "enable invalid/invalid")

        with self.assertRaises(ConnectorError):
            command.run()

        self.assertNotIn("invalid/invalid", self.odev.config.plugins.enabled, "should not enable the plugin")

    def test_command_setup(self):
        """Command `odev setup` should run the setup scripts."""

        # ----------------------------------------------------------------------
        # Run the command without arguments
        # ----------------------------------------------------------------------

        command = self.setup_command("setup")

        with CaptureOutput() as output:
            command.run()

        self.assertEqual("Hello, odev from script 1!\nHello, odev from script 2!\n", output.stdout)

        # ----------------------------------------------------------------------
        # Run the command with a category argument
        # ----------------------------------------------------------------------

        command = self.setup_command("setup", "test_setup_script_1")

        with CaptureOutput() as output:
            command.run()

        self.assertEqual("Hello, odev from script 1!\n", output.stdout)

    def test_command_update(self):
        """Command `odev update` should update the application and its dependencies."""

        from odev.commands.utilities.update import logger
        from odev._version import __version__

        # ----------------------------------------------------------------------
        # Run the command without arguments
        # ----------------------------------------------------------------------

        command = self.setup_command("update")

        with self.patch(logger, "info"):
            command.run()

        self.assertEqual(self.odev.config.update.version, __version__)

    def test_command_venv(self):
        """Command `odev venv` should interact with virtual environments created and managed by Odev."""

        # ----------------------------------------------------------------------
        # Run the command with an invalid virtual environment name
        # ----------------------------------------------------------------------

        command = self.setup_command("venv", "invalid print('test')")

        with self.assertRaisesRegex(CommandError, r"Virtual environment [\w/._-]*(invalid) does not exist"):
            command.run()

        # ----------------------------------------------------------------------
        # Run the command with a name valid argument and a python command
        # ----------------------------------------------------------------------

        PythonEnv("odev-test").create_venv()
        command = self.setup_command("venv", "odev-test print('test')")
        command.run()

        self.assertRegex(self.Popen.all_calls[-4].args[0], r"python[\d.?]+\s-c\s[\\'\"]+print[\\'\"\(]+test", "should output 'test'")

        # ----------------------------------------------------------------------
        # Run the command with a pip command
        # ----------------------------------------------------------------------

        command = self.setup_command("venv", "odev-test 'pip --version'", keep_quotes=False)
        command.run()

        self.assertRegex(self.Popen.all_calls[-4].args[0], r"python[\d.?]+\s-m\spip\s--version", "should detect pip as a module and print its version")

    def test_command_version(self):
        """Command `odev version` should print the version of the application."""

        command = self.setup_command("version")
        command.run()
