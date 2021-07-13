"""Command-line commands base classes and utility functions"""

import inspect
import logging
import sys
import textwrap
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, Action, RawTextHelpFormatter
from typing import ClassVar, MutableMapping, Type, Optional, Any, Union, Sequence, List


from .logging import set_log_level


__all__ = [
    "CommaSplitArgs",
    "ROOT",
    "CommandType",
    "CliCommand",
    "CommandsRegistryType",
    "CliCommandsSubRoot",
    "CliCommandsRoot",
    "main",
]


logger = logging.getLogger(__name__)


class CommaSplitArgs(Action):
    """
    Converter for command line arguments passed as comma-separated lists of values
    """

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence, None],
        option_string: Optional[str] = None,
    ) -> None:
        values = values.split(",") if isinstance(values, str) else values
        setattr(namespace, self.dest, values)


# TODO: Does this make sense anymore?
class _ROOT:
    """Sentinel object for root, using a class for better repr"""


ROOT = _ROOT()


CommandType = Union[str, _ROOT]


class CliCommand(ABC):
    """
    Base class for command line commands.
    """

    parent: ClassVar[Optional["CliCommandsSubRoot"]] = None
    """Parent command class. If not specified, defaults to the root parser."""
    command: ClassVar[CommandType] = None
    """The name of the command associated with the class, or ROOT. Must be unique."""
    aliases: ClassVar[Sequence[str]] = None
    """Additional aliases for the command. These too must be unique."""
    help: ClassVar[Optional[str]] = None
    """Optional help information on what the command does."""
    help_short: ClassVar[Optional[str]] = None
    """Optional short help information on what the command does.
    If omitted, the class or source module docstring will be used instead."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Handles registration of subclasses into the internal registry of commands,
        and does some misc preparation.
        """
        # TODO: consider lifting this restriction, and just skip registering
        is_abstract: bool = inspect.isabstract(cls) or ABC in cls.__bases__
        if not is_abstract:
            if cls.command is None:
                raise ValueError(f'No "command" specified on the class {cls}')
            if cls.parent is None:
                cls.parent = CliCommandsRoot if cls.command is not ROOT else cls
            if cls.command is not None:
                cls.parent.register_command(cls)
        if cls.help is not None:
            cls.help = textwrap.dedent(cls.help).strip()
        if cls.help_short is None:
            cls.help_short = cls.__doc__ or sys.modules[cls.__module__].__doc__ or None
        if cls.help_short is not None:
            cls.help_short = textwrap.dedent(cls.help_short).strip()

    @classmethod
    @abstractmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        """Prepares the argument parser for the :class:`CliCommand` subclass."""

    @classmethod
    def _prepare_parsers(cls) -> List[ArgumentParser]:
        """
        Prepares the argument parsers for the :class:`CliCommand` subclass.
        It can return one or multiple argument parsers that will be used to build
        the final argument parser for the command.

        :return: a sequence of :class:`ArgumentParser` objects.
        """
        parser: ArgumentParser = ArgumentParser(
            description=cls.help,
            add_help=False,
            formatter_class=RawTextHelpFormatter,
        )
        cls.prepare_arguments(parser)
        # FIXME: Maybe redundant?
        super_parsers: List[ArgumentParser] = []
        if hasattr(super(), "_prepare_parsers"):
            super_parsers = super()._prepare_parsers()
        return [*super_parsers, parser]

    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = args
        self.argv: Optional[Sequence[str]] = None

    @abstractmethod
    def run(self) -> Any:
        """Run the command"""

    @classmethod
    def run_with(cls, *args, **kwargs) -> Any:
        """Runs the command directly with the provided arguments, bypassing parsers"""
        # TODO: automatically fill missing args with None?
        return cls(Namespace(**dict(*args, **kwargs))).run()

    @classmethod
    def main(cls, argv: Optional[Sequence[str]] = None) -> Any:
        """
        Main entry point to run the command with the specified commandline arguments

        :param argv: a list of command line arguments.
            If omitted `sys.argv` will be used instead.
        """
        parser: ArgumentParser = ArgumentParser(
            parents=cls._prepare_parsers(),
            description=cls.help,
            formatter_class=RawTextHelpFormatter,
        )
        args: Namespace = parser.parse_args(argv)
        command: CliCommand = cls(args)
        command.argv = argv or sys.argv[1:]
        return command.run()

    # TODO: repr


CommandsRegistryType = MutableMapping[CommandType, Type["CliCommand"]]


class CliCommandsSubRoot(CliCommand, ABC):
    _subcommands: ClassVar[CommandsRegistryType] = {}
    """Internal registry of command subclasses"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        cls._subcommands = {}
        super().__init_subclass__(**kwargs)

    @classmethod
    def register_command(cls, command_cls: Type[CliCommand]):
        all_commands = [command_cls.command, *(command_cls.aliases or [])]
        conflicts: MutableMapping[str, Type[CliCommand]] = {
            name: cls._subcommands[name]
            for name in all_commands
            if name in cls._subcommands
        }
        if conflicts:
            raise NameError(
                f'{repr(command_cls)} command(s) conflict with the following one(s):\n"'
                + "\n".join(
                    f' - "{name}": {repr(conflict_cls)}'
                    for name, conflict_cls in conflicts.items()
                )
            )
        for command in all_commands:
            cls._subcommands[command] = command_cls

    @classmethod
    def get_command_cls(cls, command: str) -> Type[CliCommand]:
        """Returns the command class for the given command name"""
        try:
            return cls._subcommands.get(command)
        except KeyError:
            raise NotImplementedError(f'Got unhandled command "{command}"')

    @classmethod
    def _prepare_parsers(cls) -> Sequence[ArgumentParser]:
        return [cls._prepare_subparsers()]

    @classmethod
    def _prepare_subparsers(cls) -> ArgumentParser:
        """
        Prepares the argument parser for the main runtime entry point, using the
        internal registry of all available (loaded) commands subclasses.

        :return: the prepared :class:`ArgumentParser` instance.
        """
        super_parsers: List[ArgumentParser] = super()._prepare_parsers()
        main_parser: ArgumentParser
        main_parser = ArgumentParser(
            description=cls.help,
            formatter_class=RawTextHelpFormatter,
            add_help=False,
            parents=super_parsers,
        )
        common_parser: ArgumentParser = ArgumentParser(
            formatter_class=RawTextHelpFormatter, add_help=False
        )
        cls.prepare_arguments(common_parser)
        # Get all subcommands, filtering out aliases and root
        subcommands: Sequence[Type[CliCommand]] = [
            command_cls
            for command, command_cls in cls._subcommands.items()
            if command not in (None, ROOT) and command == command_cls.command
        ]
        if subcommands:
            subparsers = main_parser.add_subparsers(
                title="Available commands",
                dest="command",
                required=True,
            )
            command_cls: Type[CliCommand]
            for command_cls in subcommands:
                parsers: Sequence[ArgumentParser] = command_cls._prepare_parsers()
                assert isinstance(command_cls.command, str)
                subparsers.add_parser(
                    command_cls.command,
                    aliases=command_cls.aliases or [],
                    parents=[common_parser, *parsers],
                    help=command_cls.help_short or command_cls.help,
                    description=command_cls.help,
                    formatter_class=RawTextHelpFormatter,
                )
        return main_parser

    def __init__(self, args: Namespace):
        command_cls: Type[CliCommand] = self.get_command_cls(args.command)
        self.chosen_command: [CliCommand] = command_cls(args)
        super().__init__(args)

    def run(self) -> Any:
        if not isinstance(self.chosen_command, CliCommandsSubRoot):
            logger.info(
                f'Running command "{self.chosen_command}" with parsed arguments: {self.args}'
            )
        return self.chosen_command.run()


# TODO: Maybe make this ABC, so that the common arguments are defined in a concrete
#       subclass in user code
class CliCommandsRoot(CliCommandsSubRoot):
    command = ROOT
    help = """
        Automates common tasks relative to working with Odoo development databases.
        Check the complete help with examples on https://github.com/odoo-ps/psbe-ps-tech-tools/tree/odev#docs.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "-v",
            "--log-level",
            choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
            default="INFO",
            help="logging verbosity",
        )

    def __init__(self, args: Namespace):
        set_log_level(args.log_level)
        super().__init__(args)


main = CliCommandsRoot.main
