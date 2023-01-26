from odev.commands.database.kill import KillCommand
from odev.common.commands.base import CommandError
from tests.fixtures import Patch, Raises, setup_command, setup_command_class


class TestCommandSetup:
    def setup_method(self):
        """Create a new command instance for each test."""
        setup_command_class(KillCommand)

    def test_kill_invalid_database(self):
        """Test running the command with an invalid database name.
        Should raise an error if the database does not exist.
        """
        command = setup_command(KillCommand, ["invalid-database"])

        with Raises(CommandError) as error:
            command.run()

        assert error.match("Database 'invalid-database' does not exist")

    def test_kill_database_not_running(self):
        """Test running the command with an existing database.
        Should raise an error if the database is not running.
        """
        command = setup_command(KillCommand, ["postgres"])

        with Raises(CommandError) as error:
            command.run()

        assert error.match("Database 'postgres' is not running")

    def test_kill_database(self):
        """Test running the command with a running database.
        Should send SIGINT to the database.
        """
        command = setup_command(KillCommand, ["postgres"])

        with (
            Patch(command.database.process, "is_running", return_value=True),
            Patch(command.database.process, "pid", return_value=9999),
            Patch(command.database.process, "kill") as mock_kill,
        ):
            command.run()

        mock_kill.assert_called_once_with(hard=False)
