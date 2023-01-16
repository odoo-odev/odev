"""Odev base command class for CLI and programmatic use."""

import textwrap
import inspect
import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from typing import ClassVar, Dict, Optional, Sequence, Type, List, MutableMapping, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from odev.common.odev import Odev

CommandType = Type["BaseCommand"]
"""Base command type for type hinting."""


class BaseCommand(ABC):
    """Base class for handling commands."""

    name: ClassVar[str]
    """The name of the command associated with the class. Must be unique."""

    aliases: ClassVar[Sequence[str]] = []
    """The aliases of the command associated with the class. Must be unique."""

    framework: ClassVar["Odev"] = None
    """The framework instance associated with the command, provides access
    to sibling commands.
    """

    help: ClassVar[Optional[str]] = None
    """
    Optional help information on what the command does.
    """

    description: ClassVar[Optional[str]] = None
    """
    Optional short help information on what the command does.
    If omitted, the class or source module docstring will be used instead.
    """

    arguments: ClassVar[List[MutableMapping[str, Any]]] = [
        {
            "aliases": ["-v", "--log-level"],
            "choices": ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
            "default": "INFO",
            "help": "Set logging verbosity for the execution of odev.",
        },
        {
            "aliases": ["-h", "--help"],
            "dest": "show_help",
            "action": "store_true",
            "help": "Show help for the current command.",
        },
    ]
    """
    Arguments definitions to extend commands capabilities.
    """

    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = args

    @abstractmethod
    def run(self) -> None:
        """Executes the command."""
        raise NotImplementedError()

    @classmethod
    def prepare_command(cls) -> None:
        """Set proper attributes on the command class and provide inheritance from parent classes."""
        cls.name = (cls.name or cls.__name__).lower()
        cls.is_abstract = inspect.isabstract(cls) or ABC in cls.__bases__
        cls.help = textwrap.dedent(
            cls.__dict__.get("help")
            or cls.__doc__
            or cls.help
            or sys.modules[cls.__module__].__doc__
            or ""
        ).strip()
        cls.description = textwrap.dedent(cls.description or cls.help).strip()
        cls.arguments = cls.merge_arguments()

    @classmethod
    def merge_arguments(cls) -> List[MutableMapping[str, Any]]:
        """Merge arguments from parent classes."""
        merged_args: MutableMapping[str, Dict[str, Any]] = {}

        for parent_cls in cls.__reversed_mro():
            for arg in parent_cls.arguments:
                arg_name = arg.get("name", arg.get("dest", arg.get("aliases", [None])[0]))

                if arg_name is None:
                    raise ValueError(
                        f"Missing name for argument {arg}, provide at least one of `name`, `dest` or `aliases`"
                    )

                merged_arg: Dict[str, Any] = dict(merged_args.pop(arg_name, {}))
                merged_arg.update(arg)
                merged_arg.setdefault("name", arg_name)
                merged_arg.setdefault("aliases", [])

                if arg_name not in merged_arg["aliases"] and not merged_arg["aliases"][0].startswith("-"):
                    merged_arg["aliases"].insert(0, arg_name)

                merged_args[arg_name] = merged_arg

        return list(merged_args.values())

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        """Prepare arguments for the command subclass."""
        for arg in cls.arguments:
            params = dict(arg)
            params.pop("name")
            aliases = params.pop("aliases")
            parser.add_argument(*aliases, **params)

    @classmethod
    def prepare_parser(cls) -> ArgumentParser:
        """Prepare the parser for the command subclass.

        :return: instance of :class:`ArgumentParser` prepared with all the arguments
            defined in the command and in its parent's classes.
        """
        parser = ArgumentParser(
            prog=cls.name,
            description=cls.help,
            formatter_class=RawTextHelpFormatter,
            add_help=False,
        )
        cls.prepare_arguments(parser)
        return parser

    # --- Private methods ------------------------------------------------------

    @classmethod
    def __reversed_mro(cls):
        """Return the reversed MRO of the class, excluding non command-based classes."""
        for base_cls in reversed(cls.mro()):
            if issubclass(base_cls, BaseCommand):
                yield base_cls
