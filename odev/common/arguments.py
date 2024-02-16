"""Helper classes for configuring command arguments with autocompletion and validation."""

import pathlib
import re
from abc import ABC
from typing import (
    Any,
    List as ListType,
    Literal,
    MutableMapping,
    Optional,
    Union,
)


class Argument(ABC):
    """Base argument class."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[Any] = None,
        choices: Optional[ListType[Any]] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
        action: Literal[
            "store",
            "store_const",
            "store_true",
            "store_false",
            "store_int",
            "store_list",
            "store_path",
            "store_regex",
            "store_eval",
        ] = "store",
    ) -> None:
        """Initialize the argument and converts it to a mapping that can be fed to the command's
        `prepare_arguments`method.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param choices: A list of valid choices for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.

        :param action: The action to take when the argument is encountered, can be one of the following:
            - `store` to store the value.
            - `store_const` to store a constant value.
            - `store_true` to store `True` if the argument is encountered.
            - `store_false` to store `False` if the argument is encountered.
            - `store_int` to store the value as an integer.
            - `store_list` to split the value on commas and store the resulting list.
            - `store_path` to store the value as a path (see `pathlib.Path`).
            - `store_regex` to store the value as a compiled regular expression (see `re.compile`).
            - `store_eval` to store the value as the result of evaluating it as a (literal) Python expression.
        """
        self.name = name
        self.aliases = aliases
        self.description = description
        self.default = default
        self.nargs = nargs
        self.action = action
        self.choices = choices

    def to_dict(self, name: str) -> MutableMapping[str, Any]:
        """Dictionary representation of the argument to feed into the parser.
        :param name: The name of the argument, will be used if the `name` attribute is not set.
        """
        arg_dict: MutableMapping[str, Any] = {
            "name": self.name or name,
            "help": self.description,
            "action": self.action or "store",
        }

        if self.aliases is not None:
            arg_dict["aliases"] = self.aliases

        if self.default is not None:
            arg_dict["default"] = self.default

        if self.choices is not None:
            arg_dict["choices"] = self.choices

        if self.nargs is not None:
            arg_dict["nargs"] = self.nargs

        return arg_dict


class String(Argument):
    """String argument."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[str] = None,
        choices: Optional[ListType[str]] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add a string argument to the command class.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param choices: A list of valid choices for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            choices=choices,
            action="store",
        )


class Integer(Argument):
    """Integer argument."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[int] = None,
        choices: Optional[ListType[int]] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add an integer argument to the command class.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param choices: A list of valid choices for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            choices=choices,
            action="store_int",
        )


class Flag(Argument):
    """Flag with a boolean value."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[bool] = None,
    ) -> None:
        """Add a flag that has a boolean value which depends on whether it was passed in the command line.
        The default value is inverted if the flag is set.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument; a default value of `False` will result in the argument
        being set to `True` if present in the CLI arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            action="store_false" if default is True else "store_true",
        )


class List(Argument):
    """Comma-separated values stored as a list."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[ListType[Any]] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add a comma-separated list of values argument to the command class.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument, defaults to an empty list.
        :param choices: A list of valid choices for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            action="store_list",
        )


class Path(Argument):
    """Path to a file or directory."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[pathlib.Path] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add a path argument to the command class, stored as a `pathlib.Path` object.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            action="store_path",
        )


class Regex(Argument):
    """Regular expression."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[re.Pattern] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add a path argument to the command class, evaluated and stored as a regular expression.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            action="store_regex",
        )


class Eval(Argument):
    """Literal python object as evaluated by `ast.literal_eval()`."""

    def __init__(
        self,
        name: Optional[str] = None,
        aliases: Optional[ListType[str]] = None,
        description: Optional[str] = None,
        default: Optional[Any] = None,
        nargs: Optional[Union[int, Literal["*", "+", "?", "*..."]]] = None,
    ) -> None:
        """Add a python literal argument to the command class, evaluated by `ast.literal_eval()`.
        :param name: The name of the argument, will be used in the help command and in the command's class `args` attribute.
        :param aliases: The aliases for the argument.
        :param description: A description for the argument, will be displayed in the `help` command.
        :param default: The default value for the argument.
        :param nargs: The number of values the argument should accept, can be an integer value or one of the symbols:
            - `*` for zero or more values.
            - `+` for one or more values.
            - `?` for zero or one value.
            - `*...` for the remainder values that are not consumed by the previous arguments.
        """
        super().__init__(
            name=name,
            aliases=aliases,
            description=description,
            default=default,
            nargs=nargs,
            action="store_eval",
        )
