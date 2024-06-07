"""Odev base command class for CLI and programmatic use."""

import inspect
import re
import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Iterable,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from rich.console import RenderableType

from odev.common import args, string
from odev.common.actions import ACTIONS_MAPPING
from odev.common.console import TableHeader
from odev.common.errors import CommandError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.meta import OrderedClassAttributes
from odev.common.mixins.framework import OdevFrameworkMixin


if TYPE_CHECKING:
    from odev.common.odev import Odev


logger = logging.getLogger(__name__)


class Command(OdevFrameworkMixin, ABC, metaclass=OrderedClassAttributes):
    """Base class for handling commands."""

    _argv: Sequence[str] = []
    """Arguments passed to the command before parsing."""

    _name: ClassVar[str]
    """The name of the command associated with the class. Must be unique."""

    _aliases: ClassVar[Sequence[str]] = []
    """The aliases of the command associated with the class. Must be unique."""

    _help: ClassVar[str] = ""
    """Optional help information on what the command does."""

    _description: ClassVar[str] = ""
    """Optional short help information on what the command does.
    If omitted, the class or source module docstring will be used instead.
    """

    _arguments: ClassVar[MutableMapping[str, MutableMapping[str, Any]]] = defaultdict(dict)
    """Arguments definitions to extend commands capabilities."""

    _unknown_arguments_dest: Optional[str] = None
    """Key to which unknown arguments will be saved when parsed.
    If `None` and unknown arguments are found, an error will be raised.
    """

    _exclusive_arguments: ClassVar[Sequence[Sequence[str]]] = []
    """List of exclusive arguments that cannot be used together but at least on of them is required.
    Each list item is a list of argument names that are mutually exclusive.
    """

    # --------------------------------------------------------------------------
    # Arguments
    # --------------------------------------------------------------------------

    log_level = args.String(
        aliases=["-v", "--log-level"],
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "DEBUG_SQL", "NOTSET"],
        default="INFO",
        description="Set logging verbosity for the execution of odev.",
    )
    show_help = args.Flag(aliases=["-h", "--help"], description="Show help for the current command.")
    bypass_prompt = args.Flag(
        aliases=["-f", "--force"],
        description="Bypass confirmation prompts and assume a default value to all, use with caution!",
    )

    # --------------------------------------------------------------------------

    def __new__(cls, *args: Any, **kwargs: Any):
        """Initialize the command class."""
        instance = super().__new__(cls)
        instance._bypass_prompt_orig = False
        return instance

    def __init__(self, arguments: Namespace):
        """
        Initialize the command runner.
        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = arguments
        self.args.log_level = LOG_LEVEL
        self._bypass_prompt_orig = self.console.bypass_prompt
        self.console.bypass_prompt = self.args.bypass_prompt

    def __del__(self):
        """Reset the bypass prompt flag."""
        self.console.bypass_prompt = self._bypass_prompt_orig

    def __repr__(self) -> str:
        arguments = ", ".join(f"{k}={v!r}" for k, v in self.args.__dict__.items())
        return f"{self.__class__.__name__}({arguments})"

    def __str__(self) -> str:
        return self._name

    @classmethod
    def __reversed_mro(cls):
        """Return the reversed MRO of the class, excluding non command-based classes."""
        for base_cls in reversed(cls.mro()):
            if issubclass(base_cls, Command):
                yield base_cls

    @classmethod
    def is_abstract(cls) -> bool:
        """Indicates if the command is abstract. Abstract commands are not registered and cannot be executed,
        they can only be inherited from.
        """
        return inspect.isabstract(cls) or ABC in cls.__bases__

    @classmethod
    def convert_arguments(cls) -> None:
        """Convert :class:`Argument` attributes to a list of dictionaries that will later be fed
        to :class:`argparse.ArgumentParser`.
        """
        cls._arguments = defaultdict(dict)

        for parent_cls in cls.__reversed_mro():
            for argument in parent_cls.ordered_arguments_definitions():
                argument_dict = argument[1].to_dict(argument[0])
                argument_name = argument_dict["name"]
                argument_dict.setdefault("dest", cls._arguments[argument_name].get("dest", argument_name))
                argument_dict.setdefault("aliases", cls._arguments[argument_name].get("aliases", [argument_name]))

                if argument_name not in argument_dict["aliases"] and not argument_dict["aliases"][0].startswith("-"):
                    argument_dict["aliases"].insert(0, argument_name)

                cls._arguments[argument_name].update(**argument_dict)

    @classmethod
    def ordered_arguments_definitions(cls) -> List[Tuple[str, args.Argument]]:
        """List the arguments definitions for the command in their order of declaration."""
        arguments = cast(
            Iterable[Tuple[str, args.Argument]],
            inspect.getmembers(cls, lambda a: isinstance(a, args.Argument)),
        )
        return sorted(
            arguments,
            key=lambda argument: cls.member_names.index(argument[0])
            if argument[0] in cls.member_names
            else float("inf"),
        )

    @classmethod
    def prepare_command(cls, framework: "Odev") -> None:
        """Set proper attributes on the command class and provide inheritance from parent classes."""
        cls._framework = framework
        cls._name = (cls._name or cls.__name__).lower()
        cls._help = string.normalize_indent(
            cls.__dict__.get("help") or cls.__doc__ or cls._help or sys.modules[cls.__module__].__doc__ or ""
        )
        cls._description = string.normalize_indent(cls._description or cls._help)
        cls.convert_arguments()

    @classmethod
    def _find_argument(cls, name: str) -> str:
        """Find an argument by name or alias and return its actual name as registered in the class arguments mapping."""
        if name not in cls._arguments:
            argument = next(
                filter(
                    lambda arg: name in (arg["name"], arg.get("dest", ""), *arg.get("aliases", [])),
                    cls._arguments.values(),
                ),
                None,
            )

            if argument is None:
                raise KeyError(f"Argument {name!r} not found in command {cls._name!r}")

            return argument["name"]

        return name

    @classmethod
    def update_argument(cls, name: str, **values: Any) -> None:
        """Update the properties of an argument that is already registered. The can be used to update the properties
        of an argument that is inherited from a parent class.
        :param name: the name of the argument to update
        :param values: the values to update
        """
        if "description" in values:
            values["help"] = values.pop("description")

        cls._arguments[cls._find_argument(name)].update(**values)

    @classmethod
    def remove_argument(cls, name: str) -> None:
        """Remove an argument that is registered. This can e used to remove arguments from parent classes if they
        don't make sense anymore in the context of the current class.
        :param name: the name of the argument to remove.
        """
        cls._arguments.pop(cls._find_argument(name))

    @classmethod
    def check_arguments(cls, arguments: Namespace):
        """Ensure all arguments are compatible together and that they posses a correct value."""
        for exclusive_group in cls._exclusive_arguments:
            exclusive_arguments = [getattr(arguments, argument) for argument in exclusive_group]
            if sum(bool(argument) for argument in exclusive_arguments) != 1:
                raise SystemExit(
                    f"Arguments {string.join_and(exclusive_group)} are mutually exclusive and at least one is required"
                )

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        """Digest the mapping of arguments for the command subclass and add them to the parser."""
        for argument in cls._arguments.values():
            params = dict(argument)
            params.pop("name")
            aliases: Sequence[str] = params.pop("aliases")

            if params.get("nargs") == "*...":
                cls._unknown_arguments_dest = aliases[0]
                params["nargs"] = "*"

            if "action" in params:
                params["action"] = ACTIONS_MAPPING.get(params["action"], params["action"])

            if len(aliases) == 1 and aliases[0][0] != "-":
                params.pop("dest")

            parser.add_argument(*aliases, **params)

    @classmethod
    def prepare_parser(cls) -> ArgumentParser:
        """Prepare the parser for the command subclass.

        :return: instance of :class:`ArgumentParser` prepared with all the arguments
            defined in the command and in its parent's classes.
        """
        parser = ArgumentParser(
            prog=cls._name,
            description=cls._help,
            formatter_class=RawTextHelpFormatter,
            add_help=False,
        )
        cls.prepare_arguments(parser)
        return parser

    @classmethod
    def parse_arguments(cls, argv: Sequence[str]) -> Namespace:
        """Parse arguments for the command subclass.

        :param argv: the arguments to parse.
        :return: instance of :class:`Namespace` with the parsed arguments
        """
        parser = cls.prepare_parser()

        with StringIO() as stderr:
            sys.stderr = stderr

            try:
                if cls._unknown_arguments_dest is None:
                    arguments = parser.parse_args(argv)
                else:
                    arguments, unknown = parser.parse_known_args(argv)
                    setattr(arguments, cls._unknown_arguments_dest, unknown)
            except SystemExit as exception:
                error_message = stderr.getvalue()
                error = re.search(rf"{cls._name}: error: (.*)$", error_message, re.MULTILINE)
                error_message = str(error.group(1)) if error else error_message
                raise SystemExit(error_message.capitalize()) from exception
            finally:
                sys.stderr = sys.__stderr__

        for argument in cls.ordered_arguments_definitions():
            if argument[1].name not in cls._arguments and argument[0] not in cls._arguments:
                continue
            setattr(cls, argument[0], getattr(arguments, argument[1].name or argument[0]))

        return arguments

    @abstractmethod
    def run(self) -> None:
        """Executes the command."""
        raise NotImplementedError()

    def cleanup(self) -> None:
        """Cleanup after the command execution."""

    def print(
        self,
        renderable: RenderableType = "",
        file: Optional[Path] = None,
        auto_paginate: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Print to the console, allowing passthrough to a file if provided.
        :param renderable: The object to print.
        :param file: An optional file to write to instead of the console.
        :param auto_paginate: Automatically paginate the output if it doesn't fit the terminal.
        :param args: Additional arguments to pass to the print method.
        :param kwargs: Additional keyword arguments to pass to the print method.
        """
        self.console.print(renderable, file, auto_paginate, *args, **kwargs)

    def table(
        self,
        columns: Sequence[TableHeader],
        rows: Sequence[List[Any]],
        totals: Optional[List[Any]] = None,
        file: Optional[Path] = None,
        title: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Print a table to stdout with highlighting and theming.
        :param columns: The headers of the table.
        :param rows: The rows of the table.
        :param total: The total row of the table.
        :param kwargs: Additional keyword arguments to pass to the Rich Table.
        """
        self.console.table(columns, rows, totals, file, title, **kwargs)
        self.print()

    def error(self, message: str, *args: Any, **kwargs: Any) -> CommandError:
        """Build an instance of CommandError ready to be raised."""
        return CommandError(message, self, *args, **kwargs)
