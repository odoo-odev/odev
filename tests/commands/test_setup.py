from unittest.mock import patch

from odev.commands.utilities.setup import SetupCommand
from odev.common.config import ConfigManager
from odev.common.odev import Odev


class TestCommandSetup:
    def setup_method(self):
        """Create a new command instance for each test."""
        with ConfigManager("odev") as config:
            odev = Odev(config)
        SetupCommand.prepare_command(odev)

    def test_run_bare(self):
        """Test running the command without arguments."""
        command = SetupCommand(SetupCommand.parse_arguments([]))
        with patch.object(command, "run_setup") as mock_run_setup:
            mock_run_setup.return_value = None
            command.run()
        mock_run_setup.assert_called_once()

    def test_run_with_category(self):
        """Test running the command with a category argument."""
        command = SetupCommand(SetupCommand.parse_arguments(["completion"]))
        with patch.object(command, "run_setup") as mock_run_setup:
            mock_run_setup.return_value = None
            command.run()
        mock_run_setup.assert_called_once_with("completion")
