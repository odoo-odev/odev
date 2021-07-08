"""Command-line commands base classes and utility functions"""

import inspect
import logging
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, Action
from typing import ClassVar, MutableMapping, Type, Optional, Any, Union, Sequence


__all__ = [
    "CommaSplitArgs",
    "ROOT",
    "CommandType",
    "CommandsAttributeTypes",
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


class _ROOT:
    """Sentinel object for root, using a class for better repr"""


ROOT = _ROOT()


CommandType = Union[str, _ROOT]
CommandsAttributeTypes = Optional[Union[CommandType, Sequence[CommandType]]]


class CliCommand(ABC):
    """
    Base class for command line commands.
    """

    parent: ClassVar[Optional["CliCommandsSubRoot"]] = None
    """Parent command class. If not specified, defaults to the root parser."""
    command: ClassVar[CommandsAttributeTypes] = None
    """The name of the command associated with the class, or ROOT. Must be unique."""
    help: ClassVar[Optional[str]] = None
    """Optional help information on what the command does."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Handles registration of subclasses into the internal registry of commands,
        and does some misc preparation.
        """
        # TODO: consider lifting this restriction, and just skip registering
        if not inspect.isabstract(cls) and cls.command is None:
            raise ValueError('No "command" specified on the class')
        if cls.parent is None:
            cls.parent = CliCommandsRoot
        if cls.command is not None:
            cls.parent.register_command(cls)
        if cls.help is not None:
            cls.help = cls.help.strip()

    @classmethod
    @abstractmethod
    def prepare_parsers(cls) -> Sequence[ArgumentParser]:
        """
        Prepares the argument parser for the :class:`CliCommand` subclass.
        It can return one or multiple argument parsers that will be used to build
        the final argument parser for the command.

        :return: a sequence of :class:`ArgumentParser` objects.
        """

    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = args

    @abstractmethod
    def run(self) -> None:
        """Run the command"""


CommandsRegistryType = MutableMapping[CommandType, Type["CliCommand"]]


class CliCommandsSubRoot(CliCommand, ABC):
    _subcommands: ClassVar[CommandsRegistryType] = {}
    """Internal registry of command subclasses"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        cls._subcommands = {}

    @classmethod
    def register_command(cls, command_cls: Type[CliCommand]):
        commands: CommandsAttributeTypes = command_cls.command
        if isinstance(commands, (str, _ROOT)):
            commands = [commands]
        conflicts: MutableMapping[str, Type[CliCommand]] = {
            name: cls._subcommands[name]
            for name in commands
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
        for command in commands:
            cls._subcommands[command] = command_cls

    @classmethod
    def get_command_cls(cls, command: str) -> Type[CliCommand]:
        """Returns the command class for the given command name"""
        try:
            return cls._subcommands.get(command)
        except KeyError:
            raise NotImplementedError(f'Got unhandled command "{command}"')

    @classmethod
    def prepare_parsers(cls) -> Sequence[ArgumentParser]:
        return []

    @classmethod
    def prepare_main_parser(cls) -> ArgumentParser:
        """
        Prepares the argument parser for the main runtime entry point, using the
        internal registry of all available (loaded) commands subclasses.

        :return: the prepared :class:`ArgumentParser` instance.
        """
        main_parser: ArgumentParser = ArgumentParser()
        common_parsers: Sequence[ArgumentParser] = cls.prepare_parsers()
        subcommands: Sequence[Type[CliCommand]] = [
            command_cls
            for command, command_cls in cls._subcommands.items()
            if command not in (None, ROOT)
        ]
        if subcommands:
            subparsers = main_parser.add_subparsers(
                title="command",
                dest="command",
                required=True,
                help="Pick one of these subcommands",
            )
            command_cls: Type[CliCommand]
            for command_cls in subcommands:
                parsers: Sequence[ArgumentParser] = command_cls.prepare_parsers()
                assert isinstance(command_cls.command, str)
                subparsers.add_parser(
                    command_cls.command,
                    help=command_cls.help,
                    parents=[*common_parsers, *parsers],
                )
        return main_parser

    def __init__(self, args: Namespace):
        command_cls: Type[CliCommand] = self.get_command_cls(args.command)
        self.chosen_command: [CliCommand] = command_cls(args)
        super().__init__(args)

    def run(self) -> None:
        logger.info(
            f'Running command "{self.chosen_command}" with parsed arguments: {self.args}'
        )
        self.chosen_command.run()


# TODO: Maybe make this ABC, so that the common arguments are defined in a concrete
#       subclass in user code
class CliCommandsRoot(CliCommandsSubRoot):
    command = ROOT

    @classmethod
    def prepare_parsers(cls) -> Sequence[ArgumentParser]:
        parser: ArgumentParser = ArgumentParser()
        parser.add_argument(
            "-v",
            "--log-level",
            choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
            default="INFO",
            help="logging verbosity",
        )
        return [*super().prepare_parsers(), parser]

    @classmethod
    def main(cls, argv: Optional[Sequence[str]] = None) -> None:
        """
        Main entry point to run the commands specified in the given arguments

        :param argv: a list of command line arguments.
            If omitted `sys.argv` will be used instead.
        """
        parser: ArgumentParser = cls.prepare_main_parser()
        args: Namespace = parser.parse_args(argv)
        cls(args).run()


main = CliCommandsRoot.main
