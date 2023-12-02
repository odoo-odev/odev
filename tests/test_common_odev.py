import os
import sys
from pathlib import Path

from odev._version import __version__
from odev.commands.utilities.help import HelpCommand
from odev.common.odev import logger
from tests.fixtures import CaptureOutput, OdevTestCase


class TestCommonOdev(OdevTestCase):
    def test_config_file(self):
        """Config file should have been created in the correct directory."""
        self.assertEqual(self.odev.config.name, "odev-test", "name should be 'odev-test'")
        self.assertEqual(
            self.odev.config.path,
            Path.home() / ".config/odev/odev-test.cfg",
            "path should be 'test.cfg' in the config directory",
        )

    def test_config_get_set_reset_delete_value(self):
        """Config manager should be able to get, set and reset values, as well as delete a key or a section.
        An error should be raised when accessing invalid values.
        """
        self.assertEqual(self.odev.config.update.version, __version__, "should be able to get a value")
        self.odev.config.update.version = "1.0.0"
        self.assertEqual(self.odev.config.update.version, "1.0.0", "should be able to set a value and get it back")
        self.odev.config.update.reset("version")
        self.assertEqual(self.odev.config.update.version, __version__, "should be able to reset a value to its default")
        self.odev.config.update.delete("version")
        self.assertEqual(
            self.odev.config.parser.has_option("update", "version"), False, "should be able to delete a value"
        )
        self.assertRaises(KeyError, self.odev.config.get, "invalid", "key")

    def test_restart(self):
        """The restart method should replace the current process."""
        with self.patch(os, "execv") as mock_execv:
            self.odev.restart()
        mock_execv.assert_called_once()

    def test_restart_on_update(self):
        """Odev should restart itself when updated."""
        with self.patch(self.odev, "update", return_value=True), self.patch(self.odev, "restart") as mock_restart:
            self.odev.__class__.commands = {}
            self.odev.__class__.__init__(self.odev, test=self.odev.in_test_mode)
        mock_restart.assert_called_once_with()

    def test_upgrade_same_version(self):
        """The upgrade method should do nothing if the version is the same as the current version."""
        with CaptureOutput() as output:
            self.odev.upgrade()

        self.assertEqual(output.stdout, "", "should not print anything to stdout")
        self.assertEqual(
            self.odev.config.update.version, __version__, "should not update the version in the configuration file"
        )

    def test_upgrade_new_version(self):
        """The upgrade method should run upgrade scripts. with a version bigger than the current version.
        The version in the configuration file should be updated.
        """
        self.odev.config.update.version = "0.0.0"

        with CaptureOutput() as output:
            self.odev.upgrade()

        self.assertEqual(output.stdout, "Hello, odev!\n", "should print the output of the upgrade script to stdout")
        self.assertEqual(
            self.odev.config.update.version, __version__, "should update the version in the configuration file"
        )

    def test_register_duplicate(self):
        """An error should be raise if two commands share the same name."""
        with (
            self.assertRaises(ValueError) as error,
            self.patch(self.odev, "import_commands", return_value=[HelpCommand, HelpCommand]),
        ):
            self.odev.register_commands()
        self.assertEqual(
            error.exception.args[0], "Another command 'help' is already registered", "should raise a ValueError"
        )

    def test_dispatch_command(self):
        """The command should be dispatched based on the given name."""
        sys.argv = ["odev", "help"]
        help_command = self.odev.commands.get("help")
        with self.patch(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_help_default(self):
        """The help command should be dispatched by default if no command was given."""
        sys.argv = ["odev"]
        help_command = self.odev.commands.get("help")
        with self.patch(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_command_missing(self):
        """An error should be logged if the given command does not exist."""
        sys.argv = ["odev", "missing"]
        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Command 'missing' not found")

    def test_dispatch_invalid_arguments(self):
        """An error should be logged if the given arguments are invalid."""
        sys.argv = ["odev", "help", "--invalid-argument"]
        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Unrecognized arguments: --invalid-argument")

    def test_dispatch_command_error(self):
        """An error should be logged if the command raises an exception."""
        sys.argv = ["odev", "help", "invalid-command"]
        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Cannot display help for inexistent command 'invalid-command'")
