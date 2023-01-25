from pathlib import Path

from odev.commands.utilities.setup import SetupCommand
from tests.fixtures import CaptureOutput, setup_command, setup_framework


class TestCommandSetup:
    def setup_method(self):
        """Create a new command instance for each test."""
        framework = setup_framework()
        framework.setup_path = Path(__file__).parents[1] / "resources/setup"
        SetupCommand.prepare_command(framework)

    def test_setup_no_arguments(self):
        """Test running the command without arguments.
        Should run all setup scripts in the setup directory.
        """
        command = setup_command(SetupCommand)

        with CaptureOutput() as output:
            command.run()

        assert output.stdout == "Hello, odev from script 1!\nHello, odev from script 2!\n"

    def test_run_category(self):
        """Test running the command with a category argument.
        Should run a single setup script with category as name.
        """
        command = setup_command(SetupCommand, ["test_setup_script_2"])

        with CaptureOutput() as output:
            command.run()

        assert output.stdout == "Hello, odev from script 2!\n"
