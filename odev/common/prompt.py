"""Prompt for user input."""

from pathlib import Path
from typing import Optional, List, Tuple, Union

from InquirerPy import get_style, inquirer
from InquirerPy.validator import PathValidator, NumberValidator
from InquirerPy.base.control import Choice
from prompt_toolkit.validation import ValidationError


__all__ = [
    "directory",
    "clear_line",
    "secret",
    "confirm",
    "select",
    "integer",
    "float",
]


# --- Constants ----------------------------------------------------------------


MARK = "[?]"
STYLE = get_style(
    style_override=False,
    style={
        "questionmark": "fg:#af5faf bold",
        "answermark": "fg:#af5faf bold",
        "answer": "#af5faf",
        "input": "#00afaf",
        "validator": "fg:red bg: bold",
    },
)


# --- Validators ---------------------------------------------------------------


class PurportedPathValidator(PathValidator):
    """Path validator that doesn't check if the path exists."""

    def validate(self, document) -> None:
        """Check if user input is a valid path."""

        path = Path(document.text).expanduser()

        if self._is_file and path.is_dir():
            raise ValidationError(
                message=self._message,
                cursor_position=document.cursor_position,
            )

        if self._is_dir and path.is_file():
            raise ValidationError(
                message=self._message,
                cursor_position=document.cursor_position,
            )


# --- Functions ----------------------------------------------------------------


def clear_line(count: int = 1) -> None:
    """Clear up a number of lines from the terminal.
    If a count is provided, the same amount of lines will be cleared.

    :param int count: Number of lines to clear
    """

    print("\x1b[F".join(["\x1b[2K\x1b[0G" for _ in range(count + 1)]), end="")


def secret(message: str = "Password") -> Optional[str]:
    """Prompt for a secret value hidden to the reader.

    :param str message: Question to ask the user
    :return: The secret entered by the user
    :rtype: str
    """

    return inquirer.secret(
        message=message,
        mandatory=True,
        mandatory_message="A value is required",
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()


def directory(message: str, default: str = None) -> Optional[str]:
    """Prompt for a directory path.

    :param message: Question to ask the user
    :param default: Set the default text value of the prompt
    :return: Path to the directory to use
    :rtype: str or None
    """

    return inquirer.filepath(
        message=message,
        default=default,
        only_directories=True,
        validate=PurportedPathValidator(
            is_dir=True,
            message="Path must be a directory",
        ),
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()


def confirm(message: str, default: bool = False) -> bool:
    """Prompt for a confirmation.

    :param message: Question to ask the user
    :param default: Set the default text value of the prompt
    :return: True if the user confirmed, False otherwise
    :rtype: bool
    """

    return inquirer.confirm(
        message=message,
        default=default,
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()


def select(message: str, choices: List[Tuple[str, Optional[str]]], default: str = None) -> Optional[str]:
    """Prompt for a selection.

    :param message: Question to ask the user
    :param choices: List of choices to select from
        Each option is a tuple in the format `("value", "human-readable name")`
        with the name being optional (fallback to value)
    :param default: Set the default text value of the prompt
    :return: The selected choice
    :rtype: str or None
    """

    return inquirer.select(
        message=message,
        choices=[Choice(choice[0], name=choice[-1]) for choice in choices],
        default=default,
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()


def integer(
    message: str,
    default: int = None,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> Optional[int]:
    """Prompt for an integer number.

    :param message: Question to ask the user
    :param default: Set the default value of the prompt
    :param min_value: Set the minimum allowed value
    :param max_value: Set the maximum allowed value
    :return: The selected choice
    :rtype: int or None
    """

    return inquirer.number(
        message=message,
        default=default,
        min_allowed=min_value,
        max_allowed=max_value,
        validate=NumberValidator(message="Input should be an integer"),
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()


def float(
    message: str,
    default: float = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Optional[float]:
    """Prompt for a floating-point number.

    :param message: Question to ask the user
    :param default: Set the default value of the prompt
    :param min_value: Set the minimum allowed value
    :param max_value: Set the maximum allowed value
    :return: The selected choice
    :rtype: float or None
    """

    return inquirer.number(
        message=message,
        default=default,
        min_allowed=min_value,
        max_allowed=max_value,
        float_allowed=True,
        validate=NumberValidator(message="Input should be a floating point number", float_allowed=True),
        raise_keyboard_interrupt=True,
        style=STYLE,
        amark=MARK,
        qmark=MARK,
    ).execute()
