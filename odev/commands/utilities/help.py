"""Gets help about commands."""

import textwrap
from typing import List, Tuple

from odev.common import commands, string, style
from odev.common.commands.base import CommandType
from odev.common.logging import logging


logger = logging.getLogger(__name__)


HELP_ARGS_ALIASES = ["-h", "--help"]


class HelpCommand(commands.BaseCommand):
    """Display extensive help about the selected command or a generic help message
    lightly covering all available commands.
    """

    name = "help"
    aliases = ["h", "man", *HELP_ARGS_ALIASES]
    arguments = [
        {
            "aliases": ["command"],
            "nargs": "?",
            "help": "Get help about a specific command",
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
        assert self.framework

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
            raise Exception(f"Command {self.args.command} not found.")

        executable = self.framework.executable.stem
        parser = command.prepare_parser()
        usage = parser.format_usage().replace("usage:", executable).strip()

        message = f"""
            [bold {style.PURPLE}]{executable.upper()} {command.name.upper()}[/bold {style.PURPLE}]

            {{command.description}}

            [bold]Usage: [{style.CYAN}]{usage}[/{style.CYAN}][/bold]
        """

        message_indent = self.__min_indent(message)
        description = textwrap.indent(command.description, " " * message_indent)[message_indent:]
        message = message.replace("{command.description}", description)

        if command.aliases:
            aliases = f"""
                [bold]Aliases:[/bold] {', '.join(command.aliases)}
            """
            message += textwrap.indent(textwrap.dedent(aliases), " " * message_indent)

        positional_arguments: List[Tuple[str, str]] = [
            (arg.__dict__["dest"], string.normalize_indent(arg.__dict__["help"]))
            for arg in parser._positionals._group_actions
        ]

        if positional_arguments:
            arguments_list = self.__arguments_to_list(positional_arguments, message_indent)
            positionals = f"""
                [bold]Positional Arguments:[/bold]
                {arguments_list}
            """
            message += textwrap.indent(textwrap.dedent(positionals), " " * message_indent)

        optional_arguments: List[Tuple[str, str]] = [
            (", ".join(arg.__dict__["option_strings"]), string.normalize_indent(arg.__dict__["help"]))
            for arg in parser._optionals._group_actions
        ]

        if optional_arguments:
            arguments_list = self.__arguments_to_list(optional_arguments, message_indent)
            optionals = f"""
                [bold]Optional Arguments:[/bold]
                {arguments_list}
            """
            message += textwrap.indent(textwrap.dedent(optionals), " " * message_indent)

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
        commands_indent = max(len(command.name) for command in commands)
        commands_list = ("\n" * 2).join(self.__command_short_help(command, commands_indent) for command in commands)
        message_indent = self.__min_indent(message)
        commands_list = textwrap.indent(commands_list, " " * message_indent)[message_indent:]

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

    def print(self, message: str) -> None:
        """Print a message to the standard output.

        :param message: The message to print.
        """
        super().print(textwrap.dedent(message).strip())

    # --- Private Methods ------------------------------------------------------

    def __short_help(self, name: str, description: str, indent: int = 0) -> str:
        """Return the short help formatted for a name and its description.

        :param name: The name of the element.
        :param description: The description of the element.
        :param indent: The number of spaces to indent the help.
        :return: The short help of the element.
        :rtype: str
        """
        help_text = textwrap.indent(description, " " * (indent + 4))[len(name) :]
        return f"[bold]{name}[/bold]{help_text}"

    def __command_short_help(self, command: CommandType, indent: int = 0) -> str:
        """Return the short help of a command.

        :param command: The command to get the short help from.
        :param indent: The number of spaces to indent the help.
        :return: The short help of the command.
        :rtype: str
        """
        return self.__short_help(command.name, command.help, indent)

    def __min_indent(self, text: str) -> int:
        """Return the minimum indentation of a text.

        :param text: The text to get the minimum indentation from.
        :return: The minimum indentation of the text.
        :rtype: int
        """
        return min(len(line) - len(line.lstrip()) for line in text.splitlines() if line.strip())

    def __arguments_to_list(self, arguments: List[Tuple[str, str]], indent: int = 0) -> str:
        """Return the list of arguments formatted as a string.

        :param arguments: The list of arguments to format.
        :param indent: The number of spaces to indent the list.
        :return: The list of arguments formatted as a string.
        :rtype: str
        """
        arguments_indent = max(len(arg[0]) for arg in arguments)
        arguments_list: str = "\n".join([self.__short_help(*arg, arguments_indent) for arg in arguments])
        return textwrap.indent(arguments_list, " " * (indent + 8))[indent + 4 :]
