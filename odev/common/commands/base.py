"""Odev base command class for CLI and programmatic use."""

import inspect
import re
import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from io import StringIO
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Type,
)

from rich import box
from rich.console import RenderableType
from rich.table import Table

from odev.common import string
from odev.common.actions import ACTIONS_MAPPING
from odev.common.errors import CommandError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.mixins.framework import OdevFrameworkMixin


if TYPE_CHECKING:
    from odev.common.odev import Odev

CommandType = Type["Command"]


logger = logging.getLogger(__name__)


class Command(OdevFrameworkMixin, ABC):
    """Base class for handling commands."""

    argv: List[str] = []
    """Arguments passed to the command before parsing."""

    name: ClassVar[str]
    """The name of the command associated with the class. Must be unique."""

    aliases: ClassVar[Sequence[str]] = []
    """The aliases of the command associated with the class. Must be unique."""

    help: ClassVar[str] = None
    """Optional help information on what the command does."""

    description: ClassVar[str] = None
    """Optional short help information on what the command does.
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
        {
            "aliases": ["-f", "--force"],
            "dest": "bypass_prompt",
            "action": "store_true",
            "help": "Bypass confirmation prompts and assume a default value to all, use with caution!",
        },
    ]
    """Arguments definitions to extend commands capabilities."""

    _unknown_arguments_dest: Optional[str] = None
    """Key to which unknown arguments will be saved when parsed.
    If `None` and unknown arguments are found, an error will be raised.
    """

    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = args
        self.args.log_level = LOG_LEVEL

        self._bypass_prompt_orig: bool = self.console.bypass_prompt
        self.console.bypass_prompt = self.args.bypass_prompt

    def __del__(self):
        """Reset the bypass prompt flag."""
        self.console.bypass_prompt = self._bypass_prompt_orig

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.args.__dict__.items())
        return f"{self.__class__.__name__}({args})"

    def __str__(self) -> str:
        return self.name

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
    def prepare_command(cls, framework: "Odev") -> None:
        """Set proper attributes on the command class and provide inheritance from parent classes."""
        cls._framework = framework
        cls.name = (cls.name or cls.__name__).lower()
        cls.help = string.normalize_indent(
            cls.__dict__.get("help") or cls.__doc__ or cls.help or sys.modules[cls.__module__].__doc__ or ""
        )
        cls.description = string.normalize_indent(cls.description or cls.help)
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
                merged_arg.setdefault("aliases", [arg_name])

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
            aliases: Sequence[str] = params.pop("aliases")

            if params.get("nargs") == "*...":
                cls._unknown_arguments_dest = aliases[0]
                params["nargs"] = "*"

            if "action" in params:
                params["action"] = ACTIONS_MAPPING.get(params["action"], params["action"])

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

    @classmethod
    def parse_arguments(cls, argv: List[str]) -> Namespace:
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
                error = re.search(rf"{cls.name}: error: (.*)$", error_message, re.MULTILINE)
                error_message = str(error.group(1)) if error else error_message
                raise SystemExit(error_message.capitalize()) from exception
            finally:
                sys.stderr = sys.__stderr__

        return arguments

    @classmethod
    def update_argument(cls, name: str, values: MutableMapping[str, Any]) -> Optional[MutableMapping[str, Any]]:
        """Find argument by name and update its properties.

        :param name: the name of the argument to update
        :param values: the values to update
        :return: the updated argument or None if not found
        :rtype: Optional[MutableMapping[str, Any]]
        """
        for arg in cls.arguments:
            if arg["name"] == name or name in arg["aliases"]:
                arg.update(**values)
                return arg

        return None

    @classmethod
    def remove_argument(cls, name: str):
        """Remove an argument by name.

        :param name: the name of the argument to remove.
        """
        for arg in cls.arguments:
            if arg["name"] == name or name in arg["aliases"]:
                cls.arguments.remove(arg)

    @abstractmethod
    def run(self) -> None:
        """Executes the command."""
        raise NotImplementedError()

    def cleanup(self) -> None:
        """Cleanup after the command execution."""

    def print(self, renderable: RenderableType = None, *args: Any, **kwargs: Any) -> None:
        """Print to stdout with highlighting and theming."""
        if renderable is None:
            renderable = ""

        if (
            self.console.is_terminal
            and isinstance(renderable, str)
            and self.console.height < len(renderable.splitlines())
        ):
            with self.console.pager(styles=not self.console.is_dumb_terminal):
                self.console.print(renderable, *args, **kwargs)
        else:
            self.console.print(renderable, *args, **kwargs)

    def table(
        self,
        columns: Sequence[MutableMapping[str, Any]],
        rows: Sequence[List[Any]],
        total: List[Any] = None,
        **kwargs,
    ) -> None:
        """Print a table to stdout with highlighting and theming.

        :param columns: The headers of the table.
        :param rows: The rows of the table.
        :param total: The total row of the table.
        :param kwargs: Additional keyword arguments to pass to the Rich Table.
        """
        kwargs.setdefault("show_header", True)
        kwargs.setdefault("header_style", "bold")
        kwargs.setdefault("box", box.HORIZONTALS)
        table = Table(**kwargs)

        for column in columns:
            column.setdefault("justify", "left")
            column_name = column.pop("name")
            table.add_column(column_name, **column)

        for row in rows:
            if total and row == rows[-1]:
                table.add_row(*row, end_section=True)
            elif not row and table.rows:
                table.rows[-1].end_section = True
            else:
                table.add_row(*row)

        if total:
            table.add_row(*total, style="bold")

        self.console.print(table)

    def error(self, message: str, *args: Any, **kwargs: Any) -> CommandError:
        """Build an instance of CommandError ready to be raised."""
        return CommandError(message, self, *args, **kwargs)
