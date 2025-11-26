"""Gets help about commands."""

import textwrap

from rich.markup import escape

from odev.common import args, string
from odev.common.commands import Command
from odev.common.console import Colors
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class HelpCommand(Command):
    """Display extensive help about the selected command or a generic help message
    lightly covering all available commands.
    """

    _name = "help"
    _aliases = ["h", "-h", "--help"]

    command = args.String(
        nargs="?",
        description="""
        Get help about a specific command.
        Use [bold italic]odev help[/bold italic] for a list of available commands.
        """,
    )
    names_only = args.Flag(
        aliases=["-1", "--one-column", "--names-only"],
        description="List command names one per line - useful for parsing",
    )

    def run(self) -> None:
        """Print help about the available commands."""
        if self.args.names_only:
            help_text = self.command_names()
        elif self.args.command:
            help_text = self.single_command_help()
        else:
            help_text = self.all_commands_help()

        self.console.print(textwrap.dedent(help_text).strip(), highlight=False)

    def single_command_help(self) -> str:
        """Return help about a single command.

        :return: Help about a single command.
        :rtype: str
        """
        command = self.odev.commands.get(self.args.command)

        if command is None:
            raise self.error(f"Cannot display help for inexistent command '{self.args.command}'")

        executable = self.odev.name
        parser = command.prepare_parser()
        usage = escape(parser.format_usage().replace("usage:", executable).strip())

        message = f"""
            [bold {Colors.PURPLE}]{executable.upper()} {command._name.upper()}[/bold {Colors.PURPLE}]

            {{command._description}}

            [bold][underline]Usage:[/underline] [{Colors.CYAN}]{usage}[/{Colors.CYAN}][/bold]
        """

        message_indent = string.min_indent(message)
        message_options_indent = message_indent + 4
        description = string.indent(command._description, message_indent)[message_indent:]
        message = message.replace("{command._description}", description)

        if command._aliases:
            aliases = f"""
                [bold underline]Aliases:[/bold underline] {", ".join(command._aliases)}
            """
            message += string.dedent(aliases, message_options_indent - message_indent)

        positional_arguments: list[tuple[str, str]] = [
            (arg.__dict__["dest"], string.normalize_indent(arg.__dict__["help"]))
            for arg in parser._positionals._group_actions
        ]

        if positional_arguments:
            positionals = f"""
                [bold underline]Positional Arguments:[/bold underline]

                {string.format_options_list(positional_arguments, message_options_indent)}
            """
            message += string.dedent(positionals, message_options_indent - message_indent)

        optional_arguments: list[tuple[str, str]] = [
            (", ".join(arg.__dict__["option_strings"]), string.normalize_indent(arg.__dict__["help"]))
            for arg in parser._optionals._group_actions
        ]

        if optional_arguments:
            optionals = f"""
                [bold underline]Optional Arguments:[/bold underline]

                {string.format_options_list(optional_arguments, message_options_indent)}
            """
            message += string.dedent(optionals, message_options_indent - message_indent)

        return message

    def all_commands_help(self) -> str:
        """Return a summary of all commands.

        :return: A summary of all commands.
        :rtype: str
        """
        executable = self.odev.name
        message = f"""
            [bold {Colors.PURPLE}]{executable.upper()} {self.odev.version}[/bold {Colors.PURPLE}]

            [italic]Automate common tasks relative to working with Odoo development databases.[/italic]

            [bold underline]Usage:[/bold underline] [bold {Colors.CYAN}]{executable} <command> <args>[/bold {Colors.CYAN}]

            For help on a specific command, use [bold {Colors.CYAN}]{executable} <command> --help[/bold {Colors.CYAN}]

            Arguments in square brackets ('\\[arg]') are optional and can be omitted,
            arguments in curvy brackets ('{{arg}}') are options to choose from,
            arguments without brackets ('arg') are required.
        """

        commands = [command for name, command in self.odev.commands.items() if name == command._name]
        message_indent = string.min_indent(message)
        commands_list = string.indent(
            string.format_options_list(
                [
                    (
                        command._name,
                        command._help
                        + (
                            f"\nAliases: "
                            f"{string.join_and([f'[italic]{alias}[/italic]' for alias in sorted(command._aliases)])}"
                            if command._aliases
                            else ""
                        ),
                    )
                    for command in commands
                ],
                blanks=1,
            ),
            message_indent,
        )[message_indent:]

        return f"""
            {message.rstrip()}

            [bold underline]The following commands are provided:[/bold underline]

            {commands_list}
        """

    def command_names(self) -> str:
        """Print the names of all available commands, one per line.

        :return: The names of all available commands.
        :rtype: str
        """
        return "\n".join(sorted(filter(lambda name: not name.startswith("-"), self.odev.commands.keys())))
