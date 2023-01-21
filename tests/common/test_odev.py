import sys
from unittest.mock import patch

from odev.common.config import ConfigManager
from odev.common.odev import Odev, logger


class TestCommonOdev:
    def setup_method(self):
        """Create a new odev manager for each test."""
        with ConfigManager("odev") as config:
            self.odev = Odev(config)

    def test_dispatch_command(self):
        """The command should be dispatched based on the given name."""
        sys.argv = ["odev", "help"]
        help_command = self.odev.commands.get("help")
        with patch.object(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_help_default(self):
        """The help command should be dispatched by default if no command was given."""
        sys.argv = ["odev"]
        help_command = self.odev.commands.get("help")
        with patch.object(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_command_missing(self):
        """An error should be logged if the given command does not exist."""
        sys.argv = ["odev", "missing"]
        with patch.object(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Command missing not found")

    def test_dispatch_invalid_arguments(self):
        """An error should be logged if the given arguments are invalid."""
        sys.argv = ["odev", "help", "--invalid-argument"]
        with patch.object(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Unrecognized arguments: --invalid-argument")

    def test_dispatch_command_error(self):
        """An error should be logged if the command raises an exception."""
        sys.argv = ["odev", "help", "invalid-command"]
        with patch.object(logger, "critical") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Cannot display help for inexistent command 'invalid-command'")
