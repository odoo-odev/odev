"""Command-line commands base classes and utility functions"""

import inspect
import logging
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, Action
from typing import ClassVar, MutableMapping, Type, Optional, Any, Union, Sequence


__all__ = ["CommaSplitArgs", "ROOT", "CommandType", "CommandsRegistry", "CliCommand"]


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
CommandsRegistry = MutableMapping[CommandType, Type["CliCommand"]]


class CliCommand(ABC):
    """
    Base class for command line commands.
    """
    _commands_registry: ClassVar[CommandsRegistry] = {}
    """Internal registry of command subclasses"""

    command: ClassVar[Optional[CommandType]] = None
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
        if cls.command is not None:
            pre_existing_cls: Optional[Type] = cls._commands_registry.get(cls.command)
            if pre_existing_cls is not None:
                raise NameError(
                    f'{repr(cls)} has the same command "{cls.command}" '
                    f"of already registered {repr(pre_existing_cls)}"
                )
            cls._commands_registry[cls.command] = cls
        if cls.help is not None:
            cls.help = cls.help.strip()

    @classmethod
    def get_commands_registry(cls) -> CommandsRegistry:
        """Returns the internal command registry"""
        # TODO: do we need this? What about a read only view instead, like .items()
        return cls._commands_registry

    @classmethod
    @abstractmethod
    def prepare_parsers(cls) -> Sequence[ArgumentParser]:
        """
        Prepares the argument parser for the :class:`CliCommand` subclass.
        It can return one or multiple argument parsers that will be used to build
        the final argument parser for the command.

        :return: a sequence of :class:`ArgumentParser` objects.
        """

    @classmethod
    def _setup_global_arguments(cls, parser: ArgumentParser) -> None:
        """
        Setup global arguments to be used in the main runtime argument parser.

        :param parser: the main runtime :class:`ArgumentParser` instance.
        """
        parser.add_argument(
            "-v",
            "--log-level",
            choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
            default="INFO",
            help="logging verbosity",
        )

    @classmethod
    def prepare_main_parser(cls) -> ArgumentParser:
        """
        Prepares the argument parser for the main runtime entry point, using the
        internal registry of all available (loaded) commands subclasses.

        :return: the prepared :class:`ArgumentParser` instance.
        """
        # TODO: consider attaching root_parser to parents= and instead initialize
        #       a main ArgumentParser here that only does subcommands, so that
        #       we don't have to worry about the order of args in the commandline
        root_parser: ArgumentParser
        root_command_cls: Optional[Type[CliCommand]] = cls._commands_registry.get(ROOT)
        if root_command_cls is not None:
            [root_parser] = root_command_cls.prepare_parsers()
        else:
            root_parser = ArgumentParser()
        cls._setup_global_arguments(root_parser)

        subcommands: Sequence[Type[CliCommand]] = [
            command_cls
            for command, command_cls in cls._commands_registry.items()
            if command not in (None, ROOT)
        ]
        if subcommands:
            subparsers = root_parser.add_subparsers(
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
                    command_cls.command, help=command_cls.help, parents=parsers
                )

        return root_parser

    @classmethod
    def main(cls, argv: Optional[Sequence[str]] = None) -> None:
        """
        Main entry point to run the commands specified in the given arguments

        :param argv: a list of command line arguments.
            If omitted `sys.argv` will be used instead.
        """
        # TODO: consider renaming or moving this method outside of this class
        parser: ArgumentParser = cls.prepare_main_parser()
        args: Namespace = parser.parse_args(argv)

        logging.getLogger().setLevel(args.log_level)

        command_cls: Optional[Type[CliCommand]] = cls._commands_registry.get(
            args.command
        )
        if command_cls is None:
            raise NotImplementedError(f'Got unhandled command "{args.command}"')

        logger.info(f'Running command "{args.command}" with parsed arguments: {args}')
        command_cls(args).run()

    @abstractmethod
    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """

    @abstractmethod
    def run(self) -> None:
        """Run the command"""


run = CliCommand.main
