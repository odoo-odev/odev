from unittest.mock import patch

import pytest

from odev.commands.utilities.help import HelpCommand
from odev.common.commands.base import CommandError
from odev.common.config import ConfigManager
from odev.common.odev import Odev


class TestCommandHelp:
    def setup_method(self):
        """Create a new command instance for each test."""
        with ConfigManager("odev") as config:
            odev = Odev(config)
        HelpCommand.prepare_command(odev)

    def test_run_complete_help(self):
        """Test running the command without arguments."""
        command = HelpCommand(HelpCommand.parse_arguments([]))
        with patch.object(command, "all_commands_help") as mock_help:
            mock_help.return_value = ""
            command.run()
        mock_help.assert_called_once()

        result = command.all_commands_help()
        assert command.description.splitlines()[0].strip() in result

    def test_run_command_help(self):
        """Test running the command with a command argument."""
        command = HelpCommand(HelpCommand.parse_arguments(["help"]))
        assert command.args.command == "help"
        with patch.object(command, "single_command_help") as mock_help:
            mock_help.return_value = ""
            command.run()
        mock_help.assert_called_once()

        result = command.single_command_help()
        assert command.description.splitlines()[0].strip() in result

    def test_list_command_names(self):
        """Test running the command with the one-column argument."""
        command = HelpCommand(HelpCommand.parse_arguments(["--one-column"]))
        assert command.args.names_only is True
        with patch.object(command, "command_names") as mock_help:
            mock_help.return_value = ""
            command.run()
        mock_help.assert_called_once()

        result = command.command_names()
        assert command.name in result

    def test_run_with_invalid_command(self):
        """Test running the command with an invalid command argument."""
        command = HelpCommand(HelpCommand.parse_arguments(["invalid-command"]))
        assert command.args.command == "invalid-command"
        with pytest.raises(CommandError) as _:
            command.run()
