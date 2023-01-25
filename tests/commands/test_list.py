from odev.commands.utilities.list import ListCommand
from odev.common.commands import CommandError
from tests.fixtures import (
    CaptureOutput,
    Patch,
    Raises,
    setup_command,
    setup_command_class,
)


class TestCommandList:
    def setup_method(self):
        """Create a new command instance for each test."""
        setup_command_class(ListCommand)

    def get_database_info_mock(self, database: str):
        return {"name": database}

    def test_list_names_only(self):
        """Test running the command with the --names-only argument.
        Should display a list of databases.
        """
        command = setup_command(ListCommand, ["--names-only"])

        with (
            CaptureOutput() as output,
            Patch(command.psql, "query", return_value=[("test1",), ("test2",)]),
            Patch(command, "is_odoo", return_value=True),
        ):
            command.run()

        assert "test1\n" in output.stdout
        assert "\ntest2\n" in output.stdout

    def test_list_no_result(self):
        """Test running the command with no databases present in PostgreSQL.
        Should raise an error message.
        """
        command = setup_command(ListCommand)

        with Raises(CommandError) as error, Patch(command.psql, "query", return_value=[]):
            command.run()

        assert error.match("No database found")

    def test_list_expression(self):
        """Test running the command with a --expression pattern.
        Should display a list of databases matching the pattern.
        """
        command = setup_command(ListCommand, ["--expression", "test1"])

        with (
            CaptureOutput() as output,
            Patch(command.psql, "query", return_value=[("test1",), ("test2",)]),
            Patch(command, "get_database_info", side_effect=self.get_database_info_mock),
            Patch(command, "is_odoo", return_value=True),
        ):
            command.run()

        assert " test1 " in output.stdout
        assert " test2 " not in output.stdout

    def test_list_expression_no_result(self):
        """Test running the command with no database matching the --expression pattern.
        Should raise an error message.
        """
        command = setup_command(ListCommand, ["--expression", "no-match"])

        with Raises(CommandError) as error, Patch(command.psql, "query", return_value=[("test1",), ("test2",)]):
            command.run()

        assert error.match("No database found matching pattern 'no-match'")
