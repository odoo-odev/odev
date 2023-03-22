"""Interact with the terminal and the user."""

from enum import StrEnum
from pathlib import Path
from typing import (
    ClassVar,
    List,
    Optional,
    Tuple,
    Union,
)

from InquirerPy import get_style, inquirer
from InquirerPy.base.control import Choice
from InquirerPy.validator import EmptyInputValidator, NumberValidator, PathValidator
from prompt_toolkit.validation import ValidationError
from rich.console import Console as RichConsole
from rich.control import Control, ControlType
from rich.highlighter import ReprHighlighter, _combine_regex
from rich.theme import Theme


__all__ = ["Colors", "console"]


CONTROL_LINE_UP = Control((ControlType.CURSOR_UP, 1))
CONTROL_LINE_ERASE = Control((ControlType.ERASE_IN_LINE, 2))
CONTROL_CURSOR_RESET = Control((ControlType.CURSOR_MOVE_TO_COLUMN, 0))


# --- Theme --------------------------------------------------------------------
# Colors for logging levels and other objects rendered to the terminal.


class Colors(StrEnum):
    BLACK = "dim"
    CYAN = "#00afaf"
    GRAY = ""  # Default text color from terminal settings
    GREEN = "#98C379"
    PURPLE = "#af5faf"
    RED = "#ec6047"
    YELLOW = "#d19a66"


RICH_THEME_LOGGING = {
    "logging.level.critical": f"bold {Colors.RED}",
    "logging.level.debug": f"bold {Colors.GRAY}",
    "logging.level.error": f"bold {Colors.RED}",
    "logging.level.info": f"bold {Colors.CYAN}",
    "logging.level.warning": f"bold {Colors.YELLOW}",
}

RICH_THEME = Theme(
    {
        **RICH_THEME_LOGGING,
        "bar.back": "black",
        "bar.complete": Colors.PURPLE,
        "bar.finished": Colors.PURPLE,
        "bar.pulse": Colors.PURPLE,
        "progress.data.speed": Colors.CYAN,
        "progress.description": Colors.GRAY,
        "progress.download": Colors.CYAN,
        "progress.elapsed": Colors.BLACK,
        "progress.filesize.total": f"bold {Colors.CYAN}",
        "progress.filesize": Colors.CYAN,
        "progress.percentage": f"bold {Colors.PURPLE}",
        "progress.remaining": Colors.CYAN,
        "progress.spinner": Colors.PURPLE,
        "repr.boolean_false": f"italic {Colors.RED}",
        "repr.boolean_true": f"italic {Colors.GREEN}",
        "repr.call": Colors.CYAN,
        "repr.filename": Colors.PURPLE,
        "repr.none": f"italic {Colors.CYAN}",
        "repr.number_complex": Colors.CYAN,
        "repr.number": Colors.CYAN,
        "repr.odev": f"bold {Colors.CYAN}",
        "repr.path": Colors.PURPLE,
        "repr.str": Colors.CYAN,
        "repr.url": Colors.PURPLE,
        "repr.version": f"bold {Colors.CYAN}",
        "repr.package_name": f"bold {Colors.PURPLE}",
        "repr.package_op": Colors.GRAY,
        "repr.package_version": f"bold {Colors.CYAN}",
        "status.spinner": f"bold {Colors.PURPLE}",
    }
)

INQUIRER_MARK = "[?]"
INQUIRER_STYLE = get_style(
    style_override=False,
    style={
        "questionmark": f"fg:{Colors.PURPLE} bold",
        "answermark": f"fg:{Colors.PURPLE} bold",
        "answer": Colors.PURPLE,
        "input": Colors.CYAN,
        "pointer": Colors.CYAN,
        "validator": f"fg:{Colors.RED} bg: bold",
        "skipped": Colors.GRAY,
        "checkbox": Colors.CYAN,
    },
)


# --- Logging highlighter customization ----------------------------------------
# This is not useful at all, but it's fun to have. I guess...


class OdevReprHighlighter(ReprHighlighter):
    """Extension of `ReprHighlighter` to highlight odev version numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlights[-1] = _combine_regex(
            r"(?P<odev>odev)",
            r"(?P<version>([0-9]+\.){2,}[0-9]+)",
            r"(?:(?P<package_name>[\w_-]+)(?:(?P<package_op>[<>=]+)(?P<package_version>[\d.]+)))",
            self.highlights[-1],
        )


# --- Inquirer Validators ------------------------------------------------------
# Validators for inquirer prompts.


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


# --- Rich console -------------------------------------------------------------
# This is the console that will be used across the odev framework.
# Used to output messages to the terminal and to interact with the user.


class Console(RichConsole):
    """Extension of `rich.console.Console` to use pre-configured theming
    and add custom methods to interact with the terminal and the user.
    """

    _bypass_prompt: ClassVar[bool] = False
    """If True, bypass all prompts and use default values."""

    _is_live: ClassVar[bool] = False
    """If True, the console is in live mode and lines clearing will be disabled."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("theme", RICH_THEME)
        kwargs.setdefault("highlighter", OdevReprHighlighter())
        super().__init__(*args, **kwargs)

    @property
    def bypass_prompt(self) -> bool:
        """Return True if prompts should be bypassed."""
        return Console._bypass_prompt

    @bypass_prompt.setter
    def bypass_prompt(self, value: bool):
        """Set the bypass_prompt property."""
        Console._bypass_prompt = value

    @property
    def is_live(self) -> bool:
        """Return True if the console is in live mode."""
        return Console._is_live

    @is_live.setter
    def is_live(self, value: bool):
        """Set the is_live property."""
        Console._is_live = value

    def clear_line(self, count: int = 1):
        """Clear up a number of lines from the terminal.
        If a count is provided, the same amount of lines will be cleared.
        :param int count: Number of lines to clear
        """
        assert count >= 0, "count must not be negative"

        if not self.is_live:
            self.control(CONTROL_LINE_ERASE, CONTROL_CURSOR_RESET)
            # return

        for _ in range(count):
            self.control(CONTROL_LINE_UP, CONTROL_LINE_ERASE, CONTROL_CURSOR_RESET)

    def text(self, message: str, default: str = "") -> Optional[str]:
        """Prompt for some free text.
        :param message: Question to ask the user
        :param default: Set the default value of the prompt
        :return: The text entered by the user
        :rtype: str or None
        """
        if self.bypass_prompt and default:
            return default

        return inquirer.text(
            message=message,
            default=default,
            validate=EmptyInputValidator(),
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def integer(
        self,
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
        if self.bypass_prompt and default:
            return default

        return inquirer.number(
            message=message,
            default=default,
            min_allowed=min_value,
            max_allowed=max_value,
            validate=NumberValidator(
                message=f"Input should be an integer {self.__number_bounds_message(min_value, max_value)}",
            ),
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def floating(
        self,
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
        if self.bypass_prompt and default:
            return default

        return inquirer.number(
            message=message,
            default=default,
            min_allowed=min_value,
            max_allowed=max_value,
            float_allowed=True,
            validate=NumberValidator(
                message=f"Input should be a floating point number {self.__number_bounds_message(min_value, max_value)}",
                float_allowed=True,
            ),
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def secret(self, message: str = "Password") -> Optional[str]:
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
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def confirm(self, message: str, default: bool = False) -> bool:
        """Prompt for a confirmation.
        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: True if the user confirmed, False otherwise
        :rtype: bool
        """
        if self.bypass_prompt and default:
            return default

        return inquirer.confirm(
            message=message,
            default=default,
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def directory(self, message: str, default: str = None) -> Optional[str]:
        """Prompt for a directory path.
        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: Path to the directory to use
        :rtype: str or None
        """
        if self.bypass_prompt and default:
            return default

        return inquirer.filepath(
            message=message,
            default=default,
            only_directories=True,
            validate=PurportedPathValidator(message="Path must not be a file", is_dir=True),
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def filepath(self, message: str, default: str = None) -> Optional[str]:
        """Prompt for a file path.
        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: Path to the file to use
        :rtype: str or None
        """
        if self.bypass_prompt and default:
            return default

        return inquirer.filepath(
            message=message,
            default=default,
            only_directories=True,
            validate=PurportedPathValidator(message="Path must not be a directory", is_file=True),
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def select(self, message: str, choices: List[Tuple[str, Optional[str]]], default: str = None) -> Optional[str]:
        """Prompt for a selection.
        :param message: Question to ask the user
        :param choices: List of choices to select from
            Each option is a tuple in the format `("value", "human-readable name")`
            with the name being optional (fallback to value)
        :param default: Set the default text value of the prompt
        :return: The selected choice
        :rtype: str or None
        """
        if self.bypass_prompt and default:
            return default

        return inquirer.select(
            message=message,
            choices=[Choice(choice[0], name=choice[-1]) for choice in choices],
            default=default,
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def checkbox(self, message: str, choices: List[Tuple[str, Optional[str]]], defaults: List[str] = None):
        """Prompt for a checkbox selection.
        :param message: Question to ask the user
        :param choices: List of choices to select from
            Each option is a tuple in the format `("value", "human-readable name")`
            with the name being optional (fallback to value)
        :param defaults: List of choice values to select by default
        :return: The selected choice
        :rtype: str or None
        """
        defaults = defaults or []

        if self.bypass_prompt and defaults:
            return defaults

        return inquirer.checkbox(
            message=message,
            choices=[Choice(choice[0], name=choice[-1], enabled=choice[0] in defaults) for choice in choices],
            transformer=lambda selected: f"{', '.join(selected[:-1])} and {selected[-1]}" if selected else "None",
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
        ).execute()

    def __number_bounds_message(
        self, min_value: Optional[Union[int, float]], max_value: Optional[Union[int, float]]
    ) -> str:
        """Build a message for a number validator.
        :param min_value: Minimum allowed value
        :param max_value: Maximum allowed value
        :return: The message to display
        :rtype: str
        """
        message = ""

        if min_value is not None:
            message += f"greater than {min_value}"

        if max_value is not None:
            if min_value is not None:
                message += " and "

            message += f"less than {max_value}"

        return message


# --- Export the console instance ----------------------------------------------

console = Console()
