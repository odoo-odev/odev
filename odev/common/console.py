"""Interact with the terminal and the user."""

import os
import re
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Literal,
)
from warnings import deprecated

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.base.simple import BaseSimplePrompt
from InquirerPy.utils import get_style
from InquirerPy.validator import EmptyInputValidator, NumberValidator, PathValidator
from prompt_toolkit.validation import ValidationError
from rich import box
from rich.console import Console as RichConsole, RenderableType
from rich.control import Control
from rich.highlighter import ISO8601Highlighter, ReprHighlighter, _combine_regex
from rich.segment import ControlType
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme

from odev.common import string


__all__ = ["Colors", "console"]


CONTROL_LINE_UP = Control((ControlType.CURSOR_UP, 1))
CONTROL_LINE_ERASE = Control((ControlType.ERASE_IN_LINE, 2))
CONTROL_CURSOR_RESET = Control((ControlType.CURSOR_MOVE_TO_COLUMN, 0))


def resolve_styles(styles: str) -> str:
    """Resolve styles from the Rich theme, replacing highlights and named colors.
    :param str styles: The styles string to resolve.
    """
    for style in styles.split():
        if style in RICH_THEME.styles:
            styles = styles.replace(style, str(RICH_THEME.styles[style]))

    return styles


@dataclass
class TableHeader:
    """Table header definition."""

    title: str = ""
    """Title of the column."""

    min_width: int = 0
    """Minimum width of the column."""

    align: Literal["left", "center", "right"] = "left"
    """Alignment of the column."""

    style: str = ""
    """Style to apply on each element of the column."""

    def dict(self) -> dict[str, Any]:
        """Return the table header as a dictionary."""
        return {
            "header": self.title,
            "min_width": self.min_width,
            "justify": self.align,
            "style": resolve_styles(self.style),
        }


# --- Theme --------------------------------------------------------------------
# Colors for logging levels and other objects rendered to the terminal.


class Colors:
    """Terminal colors definitions to use with Rich themes."""

    BLACK = "dim"
    """Dimmed text color from terminal settings."""

    WHITE = "white"
    """White text color."""

    CYAN = "#00afaf"
    """Odoo cyan (secondary) color."""

    GRAY = ""
    """Default text color from terminal settings."""

    GREEN = "#98C379"
    """Green."""

    PURPLE = "#af5faf"
    """Odoo purple (primary) color."""

    RED = "#ec6047"
    """Red used for errors."""

    YELLOW = "#d19a66"
    """Yellow used for warnings."""

    RESET = "#"
    """Color reset."""


RICH_THEME_LOGGING = {
    "logging.level.critical": f"bold {Colors.RED}",
    "logging.level.debug": f"bold {Colors.GRAY}",
    "logging.level.error": f"bold {Colors.RED}",
    "logging.level.info": f"bold {Colors.CYAN}",
    "logging.level.warning": f"bold {Colors.YELLOW}",
}

RICH_THEME_COLORS = {
    "color.black": Colors.BLACK,
    "color.cyan": Colors.CYAN,
    "color.gray": Colors.GRAY,
    "color.green": Colors.GREEN,
    "color.purple": Colors.PURPLE,
    "color.red": Colors.RED,
    "color.yellow": Colors.YELLOW,
    "color.white": Colors.WHITE,
}

RICH_THEME = Theme(
    {
        **RICH_THEME_LOGGING,
        **RICH_THEME_COLORS,
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
        "repr.brace": Colors.GRAY,
        "repr.call": Colors.CYAN,
        "repr.ellipsis": Colors.GRAY,
        "repr.filename": Colors.PURPLE,
        "repr.ipv4": Colors.CYAN,
        "repr.none": f"italic {Colors.CYAN}",
        "repr.number_complex": Colors.CYAN,
        "repr.number": Colors.CYAN,
        "repr.odev": f"bold {Colors.CYAN}",
        "repr.package_name": f"bold {Colors.PURPLE}",
        "repr.package_op": Colors.GRAY,
        "repr.package_version": f"bold {Colors.CYAN}",
        "repr.path": Colors.PURPLE,
        "repr.str": Colors.CYAN,
        "repr.url": Colors.PURPLE,
        "repr.version": Colors.CYAN,
        "repr.time": f"bold {Colors.CYAN}",
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
        self.highlights: list[str] = [
            *self.highlights[:-1],
            *ISO8601Highlighter.highlights,
            _combine_regex(
                r"(?P<version>(?:[0-9]+\.){2,}[0-9]+)",
                self.highlights[-1],
            ),
        ]


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

    @deprecated("Use `force_bypass_prompt` instead.")
    @contextmanager
    def no_bypass_prompt(self):
        """Context manager to temporarily disable prompt bypassing."""
        with self.force_bypass_prompt(force=False):
            yield

    @contextmanager
    def force_bypass_prompt(self, force: bool = False):
        """Context manager to temporarily force prompt bypassing."""
        original_bypass = self.bypass_prompt
        self.bypass_prompt = force
        yield
        self.bypass_prompt = original_bypass

    def clear_line(self, count: int = 1):
        """Clear up a number of lines from the terminal.

        If a count is provided, the same amount of lines will be cleared.
        :param int count: Number of lines to clear
        """
        if count < 0:
            raise ValueError("Count must not be negative")

        if not self.is_live:
            self.control(CONTROL_LINE_ERASE, CONTROL_CURSOR_RESET)

        for _ in range(count):
            self.control(CONTROL_LINE_UP, CONTROL_LINE_ERASE, CONTROL_CURSOR_RESET)

    def _print_to_file(self, renderable: RenderableType, file: Path, *args: Any, **kwargs: Any) -> None:
        """Print to a file.
        :param renderable: The object to print.
        :param file: The file to print to.
        :param args: Additional arguments to pass to the print method.
        :param kwargs: Additional keyword arguments to pass to the print method.
        """
        pause_live = self.is_live

        if pause_live:
            self.pause_live()

        console_file = self.file  # type: ignore [has-type]
        file.resolve().parent.mkdir(parents=True, exist_ok=True)
        kwargs["highlight"] = False

        with file.open("wt", encoding="utf-8") as buffer:
            self.file = buffer
            super().print(renderable, *args, **kwargs)

        self.file = console_file

        if pause_live:
            self.resume_live()

    def print(
        self,
        renderable: RenderableType = "",
        file: Path | None = None,
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
        if isinstance(renderable, str):
            renderable = string.resolve_styles(renderable)

        if "style" in kwargs:
            kwargs["style"] = resolve_styles(kwargs["style"])

        if file is not None:
            self._print_to_file(renderable, file, *args, **kwargs)
            return

        if (
            self.is_terminal
            and isinstance(renderable, str)
            and self.height < len(renderable.splitlines())
            and auto_paginate
        ):
            pager = os.environ.get("PAGER", "")
            less = os.environ.get("LESS", "")

            if pager != "less":
                os.environ["PAGER"] = "less"

            if not re.match(r"-\w*R", less):
                os.environ["LESS"] = f"{less} -R"

            with self.pager(styles=not self.is_dumb_terminal):
                super().print(renderable, *args, **kwargs)

            os.environ["PAGER"] = pager
            os.environ["LESS"] = less
        else:
            super().print(renderable, *args, **kwargs)

    def table(
        self,
        headers: Sequence[TableHeader],
        rows: Sequence[list[Any]],
        totals: list[Any] | None = None,
        file: Path | None = None,
        title: str | None = None,
        **kwargs,
    ) -> None:
        """Print a table to stdout with highlighting and theming.
        :param columns: The headers of the table.
        :param rows: The rows of the table.
        :param total: The total row of the table.
        :param kwargs: Additional keyword arguments to pass to the Rich Table.
        """
        if title is not None:
            rule_char: str = "─"
            self.rule(
                f"{rule_char} {string.stylize(title, 'bold color.cyan')}",
                align="left",
                style="",
                characters=rule_char,
            )
            return self.table(headers, rows, totals, show_header=any(header.title for header in headers), box=None)

        kwargs.setdefault("show_header", True)
        kwargs.setdefault("header_style", "bold" if file is None else None)
        kwargs.setdefault("box", box.HORIZONTALS)
        kwargs.setdefault("padding", (0, 3))
        kwargs.setdefault("collapse_padding", True)
        table = Table(**kwargs)

        for header in headers:
            table.add_column(**header.dict())

        for row in rows:
            if totals and row == rows[-1]:
                table.add_row(*row, end_section=True)
            elif not row and table.rows:
                table.rows[-1].end_section = True
            else:
                table.add_row(*row)

        if totals:
            table.add_row(*totals, style="bold" if file is None else None)

        return self.print(table, file=file, crop=not file, overflow="ignore", no_wrap=True)

    def code(self, text: str, language: str = "python", file: Path | None = None, **kwargs):
        """Display a code block.

        :param text: Code to display.
        :param language: Language of the code.
        :param kwargs: Keyword arguments to pass to `rich.syntax.Syntax`.
        """
        if file is not None:
            self.print(
                text,
                file=file,
                highlight=False,
                crop=False,
                no_wrap=True,
                overflow="ignore",
                end="",
                **kwargs,
            )
            return

        kwargs.setdefault("background_color", "default")
        kwargs.setdefault("theme", "github-dark")
        self.print(Syntax(text, language, **kwargs))

    def __prompt_factory(self, prompt_type: type[BaseSimplePrompt], message: str, **kwargs) -> Any:
        """Create a prompt object.
        :param prompt_type: Type of prompt to create.
        :param message: Prompt message.
        :param kwargs: Keyword arguments to pass to the prompt constructor.
        :return: The result of the prompt.
        """
        self.pause_live()
        prompt = prompt_type(
            raise_keyboard_interrupt=True,
            style=INQUIRER_STYLE,
            amark=INQUIRER_MARK,
            qmark=INQUIRER_MARK,
            message=message,
            **kwargs,
        )
        original_run = prompt._run

        def patched_run():
            if self.bypass_prompt:
                default_key = "defaults" if prompt_type == "checkbox" else "default"

                if default_key in kwargs:
                    prompt.status = {
                        "answered": True,
                        "result": kwargs[default_key],
                        "skipped": False,
                    }

                    prompt_message: list[tuple[str, str]] = prompt._get_prompt_message()  # type: ignore [call_args]
                    question: str = next(m for m in prompt_message if m[0] == "class:answered_question")[1].strip()
                    answer: str = next(m for m in prompt_message if m[0] == "class:answer")[1].strip()

                    self.print(
                        f"{string.stylize(INQUIRER_MARK, 'bold color.purple')} "
                        f"{question} {string.stylize(answer, 'color.purple')}",
                        highlight=False,
                    )
                    return kwargs[default_key]

            return original_run()

        prompt._run = patched_run
        result = prompt.execute()
        self.resume_live()
        return result

    def text(self, message: str, default: str = "") -> str:
        """Prompt for some free text.

        :param message: Question to ask the user
        :param default: Set the default value of the prompt
        :return: The text entered by the user
        :rtype: str
        """
        return self.__prompt_factory(
            inquirer.text,
            message=message,
            default=default,
            validate=EmptyInputValidator(),
        )

    def integer(
        self,
        message: str,
        default: int | None = None,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int | None:
        """Prompt for an integer number.

        :param message: Question to ask the user
        :param default: Set the default value of the prompt
        :param min_value: Set the minimum allowed value
        :param max_value: Set the maximum allowed value
        :return: The selected choice
        :rtype: int or None
        """
        return self.__prompt_factory(
            inquirer.number,
            message=message,
            default=default,
            min_allowed=min_value,
            max_allowed=max_value,
            validate=NumberValidator(
                message=f"Input should be an integer {self.__number_bounds_message(min_value, max_value)}",
            ),
        )

    def floating(
        self,
        message: str,
        default: float | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> float | None:
        """Prompt for a floating-point number.

        :param message: Question to ask the user
        :param default: Set the default value of the prompt
        :param min_value: Set the minimum allowed value
        :param max_value: Set the maximum allowed value
        :return: The selected choice
        :rtype: float or None
        """
        return self.__prompt_factory(
            inquirer.number,
            message=message,
            default=default,
            min_allowed=min_value,
            max_allowed=max_value,
            float_allowed=True,
            validate=NumberValidator(
                message=f"Input should be a floating point number {self.__number_bounds_message(min_value, max_value)}",
                float_allowed=True,
            ),
        )

    def secret(self, message: str = "Password") -> str:
        """Prompt for a secret value hidden to the reader.

        :param str message: Question to ask the user
        :return: The secret entered by the user
        :rtype: str
        """
        return self.__prompt_factory(
            inquirer.secret,
            message=message,
            mandatory=True,
            mandatory_message="A value is required",
        )

    def confirm(self, message: str, default: bool = False) -> bool:
        """Prompt for a confirmation.

        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: True if the user confirmed, False otherwise
        :rtype: bool
        """
        return self.__prompt_factory(
            inquirer.confirm,
            message=message,
            default=default,
        )

    def directory(self, message: str, default: str | None = None) -> str | None:
        """Prompt for a directory path.

        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: Path to the directory to use
        :rtype: str or None
        """
        return self.__prompt_factory(
            inquirer.filepath,
            message=message,
            default=default,
            only_directories=True,
            validate=PurportedPathValidator(message="Path must not be a file", is_dir=True),
        )

    def filepath(self, message: str, default: str | None = None) -> str | None:
        """Prompt for a file path.

        :param message: Question to ask the user
        :param default: Set the default text value of the prompt
        :return: Path to the file to use
        :rtype: str or None
        """
        return self.__prompt_factory(
            inquirer.filepath,
            message=message,
            default=default,
            only_directories=True,
            validate=PurportedPathValidator(message="Path must not be a directory", is_file=True),
        )

    def select(
        self, message: str, choices: Sequence[tuple[Any | None, str | None]], default: Any | None = None
    ) -> Any | None:
        """Prompt for a selection.

        :param message: Question to ask the user
        :param choices: List of choices to select from
            Each option is a tuple in the format `("value", "human-readable name")`
            with the name being optional (fallback to value)
        :param default: Set the default text value of the prompt
        :return: The selected choice
        :rtype: str or None
        """
        return self.__prompt_factory(
            inquirer.select,
            message=message,
            choices=[Choice(choice[0], name=choice[-1]) for choice in choices],
            default=default,
        )

    def checkbox(self, message: str, choices: Sequence[tuple[Any, str | None]], defaults: Sequence[Any] | None = None):
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

        return self.__prompt_factory(
            inquirer.checkbox,
            message=message,
            choices=[Choice(choice[0], name=choice[-1], enabled=choice[0] in defaults) for choice in choices],
            transformer=lambda selected: string.join_and(selected) if selected else "None",
        )

    def fuzzy(self, message: str, choices: Sequence[tuple[str, str | None]], default: str | None = None) -> Any | None:
        """Prompt for a fuzzy selection.

        :param message: Question to ask the user
        :param choices: List of choices to select from
            Each option is a tuple in the format `("value", "human-readable name")`
            with the name being optional (fallback to value)
        :param default: Set the default text value of the prompt
        :return: The selected choice
        :rtype: str or None
        """
        return self.__prompt_factory(
            inquirer.fuzzy,
            message=message,
            choices=[Choice(choice[0], name=choice[-1]) for choice in choices],
            default=default,
            max_height=10,
            match_exact=True,
            exact_symbol="",
        )

    def __number_bounds_message(self, min_value: int | float | None, max_value: int | float | None) -> str:
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

    def pause_live(self):
        """Stop the current live status to perform any pre-prompt actions."""
        from odev.common.progress import StackedStatus  # noqa: PLC0415 # avoid circular import

        StackedStatus.pause_stack()

    def resume_live(self):
        """Resume the current live status to perform any post-prompt actions."""
        from odev.common.progress import StackedStatus  # noqa: PLC0415 # avoid circular import

        StackedStatus.resume_stack()


# --- Export the console instance ----------------------------------------------

console = Console()
