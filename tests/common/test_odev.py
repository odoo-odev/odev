import os
import shutil
import sys
from pathlib import Path

import pytest

from odev.commands.utilities.help import HelpCommand
from odev.common.config import ConfigManager
from odev.common.odev import Odev, logger
from tests.fixtures import CaptureOutput, Patch, Raises


class TestCommonOdev:
    def setup_method(self):
        """Create a new odev manager for each test."""
        with ConfigManager("odev") as config:
            self.odev = Odev(config)

    @pytest.fixture(scope="session")
    def setup_config(self):
        """Fixture responsible of creating a configuration file with the default values."""
        path = Path("/tmp/odev-tests")
        path.mkdir(parents=True, exist_ok=True)

        with ConfigManager("test") as config:
            config.set("update", "version", "0.0.0")
            yield config

        shutil.rmtree(path, ignore_errors=True)
        config.path.unlink()

    def test_restart(self):
        """The restart method should replace the current process."""
        with Patch(os, "execv") as mock_execv:
            self.odev.restart()
        mock_execv.assert_called_once()

    def test_restart_on_update(self):
        """Odev should restart itself when updated."""
        with Patch(self.odev, "update", return_value=True), Patch(self.odev, "restart") as mock_restart:
            self.odev.__init__(self.odev.config)
        mock_restart.assert_called_once_with()

    def test_upgrade_same_version(self, setup_config):
        """The upgrade method should do nothing if the version is the same as the current version."""
        odev = Odev(setup_config)
        odev.upgrades_path = Path(__file__).parents[1] / "resources/upgrade"
        odev.version = "0.0.0"

        with CaptureOutput() as output:
            odev.upgrade()

        assert output.stdout == ""
        assert setup_config.get("update", "version") == "0.0.0"

    def test_upgrade_new_version(self, setup_config):
        """The upgrade method should run upgrade scripts. with a version bigger than the current version.
        The version in the configuration file should be updated.
        """
        odev = Odev(setup_config)
        odev.upgrades_path = Path(__file__).parents[1] / "resources/upgrade"
        odev.version = "1.0.0"

        with CaptureOutput() as output:
            odev.upgrade()

        assert output.stdout == "Hello, odev!\n"
        assert setup_config.get("update", "version") == "1.0.0"

    def test_register_duplicate(self):
        """An error should be raise if two commands share the same name."""
        with (
            Raises(ValueError) as error,
            Patch(self.odev, "import_commands", return_value=[HelpCommand, HelpCommand]),
        ):
            self.odev.register_commands()
        assert error.match("Another command 'help' is already registered")

    def test_dispatch_command(self):
        """The command should be dispatched based on the given name."""
        sys.argv = ["odev", "help"]
        help_command = self.odev.commands.get("help")
        with Patch(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_help_default(self):
        """The help command should be dispatched by default if no command was given."""
        sys.argv = ["odev"]
        help_command = self.odev.commands.get("help")
        with Patch(help_command, "run") as mock_run:
            self.odev.dispatch()
        mock_run.assert_called_once_with()

    def test_dispatch_command_missing(self):
        """An error should be logged if the given command does not exist."""
        sys.argv = ["odev", "missing"]
        with Patch(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Command 'missing' not found")

    def test_dispatch_invalid_arguments(self):
        """An error should be logged if the given arguments are invalid."""
        sys.argv = ["odev", "help", "--invalid-argument"]
        with Patch(logger, "error") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Unrecognized arguments: --invalid-argument")

    def test_dispatch_command_error(self):
        """An error should be logged if the command raises an exception."""
        sys.argv = ["odev", "help", "invalid-command"]
        with Patch(logger, "critical") as mock_error:
            self.odev.dispatch()
        mock_error.assert_called_once_with("Cannot display help for inexistent command 'invalid-command'")
