"""Prompt for user input."""

from pathlib import Path
from typing import Optional

from InquirerPy import get_style, inquirer
from InquirerPy.validator import PathValidator
from prompt_toolkit.validation import ValidationError


__all__ = ["directory", "clear_line", "secret", "confirm"]


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
