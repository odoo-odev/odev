from odev.commands.utilities.help import HelpCommand
from odev.common.commands import CommandError
from tests.fixtures import CaptureOutput, Raises, setup_command, setup_command_class


class TestCommandHelp:
    def setup_method(self):
        """Create a new command instance for each test."""
        setup_command_class(HelpCommand)

    def test_help_no_args(self):
        """Test running the command without arguments.
        Should display extended help with a list of commands.
        """
        command = setup_command(HelpCommand, [])

        with CaptureOutput() as output:
            command.run()

        assert "The following commands are provided:" in output.stdout

    def test_help_command_help(self):
        """Test running the command with a command argument.
        Should display the help for the specified command.
        """
        command = setup_command(HelpCommand, ["help"])

        with CaptureOutput() as output:
            command.run()

        assert command.help in output.stdout

    def test_help_command_invalid(self):
        """Test running the command with an invalid command argument.
        Should raise a CommandError with a message about the command not existing.
        """
        command = setup_command(HelpCommand, ["invalid-command"])

        with Raises(CommandError) as error:
            command.run()

        assert error.match("Cannot display help for inexistent command 'invalid-command'")

    def test_help_command_names_only(self):
        """Test running the command with the --names-only argument.
        Should display a list of command names.
        """
        command = setup_command(HelpCommand, ["--names-only"])

        with CaptureOutput() as output:
            command.run()

        assert f"{command.name}\n" in output.stdout
