from odev.common.errors import CommandError
from tests.fixtures import CaptureOutput, OdevTestCase


class TestUtilCommands(OdevTestCase):
    def test_command_help_no_args(self):
        """Test running the command without arguments.
        Should display extended help with a list of commands.
        """
        command = self.setup_command("help")

        with CaptureOutput() as output:
            command.run()

        self.assertIn("The following commands are provided:", output.stdout)

    def test_command_help_existing_command(self):
        """Test running the command with a command argument.
        Should display the help for the specified command.
        """
        command = self.setup_command("help", "help")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(self.odev.commands["help"].help, output.stdout)

    def test_command_help_invalid_command(self):
        """Test running the command with an invalid command argument.
        Should raise a CommandError with a message about the command not existing.
        """
        command = self.setup_command("help", "invalid-command")

        with (
            self.assertRaises(CommandError, msg="Cannot display help for inexistent command 'invalid-command'"),
            # self.patch(logger, "error") as mock_error,
        ):
            command.run()

        # mock_error.assert_called_once_with("Cannot display help for inexistent command 'invalid-command'")

    def test_command_help_names_only(self):
        """Test running the command with the --names-only argument.
        Should display a list of command names.
        """
        command = self.setup_command("help", "--names-only")

        with CaptureOutput() as output:
            command.run()

        self.assertIn("help\n", output.stdout)

    def test_command_setup_all_scripts(self):
        """Test running the command without arguments.
        Should run all setup scripts in the setup directory.
        """
        command = self.setup_command("setup")

        with CaptureOutput() as output:
            command.run()

        self.assertEqual("Hello, odev from script 1!\nHello, odev from script 2!\n", output.stdout)

    def test_command_setup_category_script(self):
        """Test running the command with a category argument.
        Should run a single setup script with category as name.
        """
        command = self.setup_command("setup", "test_setup_script_1")

        with CaptureOutput() as output:
            command.run()

        self.assertEqual("Hello, odev from script 1!\n", output.stdout)

    def test_command_list_names_only(self):
        """Test running the command with the --names-only argument.
        Should display a list of databases.
        """
        command = self.setup_command("list", "--names-only --all")

        with (
            CaptureOutput() as output,
            self.patch(command.psql, "query", return_value=[("test1",), ("test2",)]),
        ):
            command.run()

        self.assertIn("test1\ntest2\n", output.stdout)

    def test_command_list_no_result(self):
        """Test running the command with no databases present in PostgreSQL.
        Should print an error message.
        """
        command = self.setup_command("list")

        with (
            self.assertRaises(CommandError, msg="No database found"),
            self.patch(command.psql, "query", return_value=[]),
        ):
            command.run()

    def test_command_list_expression(self):
        """Test running the command with a --expression pattern.
        Should display a list of databases matching the pattern.
        """
        command = self.setup_command("list", "--expression test1 --names-only --all")

        with (
            CaptureOutput() as output,
            self.patch(command.psql, "query", return_value=[("test1",), ("test2",)]),
            self.patch(command, "get_database_info", side_effect=lambda _, database: {"name": database}),
        ):
            command.run()

        self.assertIn("test1\n", output.stdout)
        self.assertNotIn("test2\n", output.stdout)

    def test_command_list_expression_no_result(self):
        """Test running the command with no database matching the --expression pattern.
        Should raise an error message.
        """
        command = self.setup_command("list", "--expression no-match --names-only --all")

        with (
            self.assertRaises(CommandError, msg="No database found matching pattern 'no-match'"),
            self.patch(command.psql, "query", return_value=[("test1",), ("test2",)]),
        ):
            command.run()

    def test_command_config_no_args(self):
        """Test running the command without arguments.
        Should display the entire configuration.
        """
        command = self.setup_command("config")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertIn(" date ", output.stdout)
        self.assertIn(" version ", output.stdout)
        self.assertIn(" interval ", output.stdout)
        self.assertIn(" dumps ", output.stdout)
        self.assertIn(" repositories ", output.stdout)

    def test_command_config_section_only(self):
        """Test running the command with a section.
        Should display the entire configuration for a specific section.
        """
        command = self.setup_command("config", "paths")

        with CaptureOutput() as output:
            command.run()

        self.assertNotIn(" mode ", output.stdout)
        self.assertNotIn(" date ", output.stdout)
        self.assertNotIn(" version ", output.stdout)
        self.assertNotIn(" interval ", output.stdout)
        self.assertIn(" dumps ", output.stdout)
        self.assertIn(" repositories ", output.stdout)

    def test_command_config_section_key(self):
        """Test running the command with a section and a key.
        Should display the configuration for a specific section/key combination only.
        """
        command = self.setup_command("config", "update.mode")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertNotIn(" date ", output.stdout)
        self.assertNotIn(" version ", output.stdout)
        self.assertNotIn(" interval ", output.stdout)
        self.assertNotIn(" dumps ", output.stdout)
        self.assertNotIn(" repositories ", output.stdout)

    def test_command_config_section_invalid(self):
        """Test running the command with a section and a key, but invalid.
        Should display the configuration for a specific section/key combination only.
        """
        command = self.setup_command("config", "test")

        with self.assertRaises(CommandError, msg=f"'test' is not a valid section in config {self.odev.config.name!r}"):
            command.run()

    def test_command_config_set_section_key_value(self):
        """Test running the command with a section, a key and a value.
        Should update the configuration with the selected value.
        """
        self.odev.config.update.mode = "ask"
        command = self.setup_command("config", "update.mode always")

        with CaptureOutput() as output:
            command.run()

        self.assertIn(" mode ", output.stdout)
        self.assertEqual(self.odev.config.update.mode, "always")

    def test_command_config_set_section_no_key(self):
        """Test running the command with a section, a key and a value.
        Should update the configuration with the selected value.
        """
        self.odev.config.update.mode = "ask"
        command = self.setup_command("config", "update mode")

        with self.assertRaises(CommandError, msg="You must specify a key to set a value"):
            command.run()
