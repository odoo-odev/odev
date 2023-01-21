"""Gets help about commands."""

import textwrap
from typing import List, Tuple

from rich.markup import escape

from odev.common import string, style
from odev.common.commands import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class HelpCommand(Command):
    """Display extensive help about the selected command or a generic help message
    lightly covering all available commands.
    """

    name = "help"
    aliases = ["h", "man", "-h", "--help"]
    arguments = [
        {
            "aliases": ["command"],
            "nargs": "?",
            "help": """
                Get help about a specific command.
                Use [bold italic]odev help[/bold italic] for a list of available commands.
            """,
        },
        {
            "aliases": ["-1", "--one-column", "--names-only"],
            "dest": "names_only",
            "action": "store_true",
            "help": "List command names one per line - useful for parsing",
        },
    ]

    def run(self) -> None:
        """Print help about the available commands."""
        if self.args.names_only:
            help_text = self.command_names()
        elif self.args.command:
            help_text = self.single_command_help()
        else:
            help_text = self.all_commands_help()

        self.print(help_text)

    def single_command_help(self) -> str:
        """Return help about a single command.

        :return: Help about a single command.
        :rtype: str
        """
        command = self.framework.commands.get(self.args.command)

        if command is None:
            raise self.error(f"Cannot display help for inexistent command '{self.args.command}'")

        executable = self.framework.executable.stem
        parser = command.prepare_parser()
        usage = escape(parser.format_usage().replace("usage:", executable).strip())

        message = f"""
            [bold {style.PURPLE}]{executable.upper()} {command.name.upper()}[/bold {style.PURPLE}]

            {{command.description}}

            [bold][underline]Usage:[/underline] [{style.CYAN}]{usage}[/{style.CYAN}][/bold]
        """

        message_indent = string.min_indent(message)
        message_options_indent = message_indent + 4
        description = string.indent(command.description, message_indent)[message_indent:]
        message = message.replace("{command.description}", description)

        if command.aliases:
            aliases = f"""
                [bold underline]Aliases:[/bold underline] {', '.join(command.aliases)}
            """
            message += string.dedent(aliases, message_options_indent - message_indent)

        positional_arguments: List[Tuple[str, str]] = [
            (arg.__dict__["dest"], string.normalize_indent(arg.__dict__["help"]))
            for arg in parser._positionals._group_actions
        ]

        if positional_arguments:
            positionals = f"""
                [bold underline]Positional Arguments:[/bold underline]

                {string.format_options_list(positional_arguments, message_options_indent)}
            """
            message += string.dedent(positionals, message_options_indent - message_indent)

        optional_arguments: List[Tuple[str, str]] = [
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
        executable = self.framework.executable.stem
        message = f"""
            [bold {style.PURPLE}]{executable.upper()} {self.framework.version}[/bold {style.PURPLE}]

            [italic]Automate common tasks relative to working with Odoo development databases.[/italic]

            [bold underline]Usage:[/bold underline] [bold {style.CYAN}]{executable} <command> <args>[/bold {style.CYAN}]

            For help on a specific command, use [bold {style.CYAN}]{executable} <command> --help[/bold {style.CYAN}]

            Arguments in square brackets ('\\[arg]') are optional and can be omitted,
            arguments in curvy brackets ('{{arg}}') are options to choose from,
            arguments without brackets ('arg') are required.
        """

        commands = [command for name, command in self.framework.commands.items() if name == command.name]
        message_indent = string.min_indent(message)
        commands_list = string.indent(
            string.format_options_list([(command.name, command.help) for command in commands], blanks=1),
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
        return "\n".join(sorted(filter(lambda name: not name.startswith("-"), self.framework.commands.keys())))

    def print(self, text: str, *args, **kwargs) -> None:
        """Print a message to the standard output.

        :param message: The message to print.
        """
        super().print(textwrap.dedent(text).strip(), *args, **kwargs)
