import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from odev.commands.utilities.setup import SetupCommand
from odev.common.config import ConfigManager
from odev.common.odev import Odev


class TestCommandSetup:
    def setup_method(self):
        """Create a new command instance for each test."""
        with ConfigManager("odev") as config:
            odev = Odev(config)
            odev.setup_path = Path(__file__).parents[1] / "resources/setup"
        SetupCommand.prepare_command(odev)

    def test_run_bare(self):
        """Test running the command without arguments."""
        command = SetupCommand(SetupCommand.parse_arguments([]))
        with patch.object(command, "run_setup") as mock_run_setup:
            command.run()
        mock_run_setup.assert_called_once()

    def test_run_with_category(self):
        """Test running the command with a category argument."""
        command = SetupCommand(SetupCommand.parse_arguments(["test_setup_script"]))

        with StringIO() as stdout:
            sys.stdout = stdout
            command.run()
            value = stdout.getvalue()
            sys.stdout = sys.__stdout__
        assert value == "Hello, odev!\n", "script should return the correct output"

        with patch.object(command, "run_setup") as mock_run_setup:
            command.run()
        mock_run_setup.assert_called_once_with("test_setup_script")
