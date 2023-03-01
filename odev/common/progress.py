"""Statuses list to keep track of all active spinners and prevent them from being
stacked on top of each other.
"""

from typing import ClassVar, List

from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress as RichProgress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.status import Status

from odev.common.logging import logging
from odev.common.style import console, repr_console


logger = logging.getLogger(__name__)


class Progress(RichProgress):
    """Progress bar that displays the log level symbol on the left.
    Also pauses running spinners when starting the progress bar to avoid errors about
    having multiple live displays at once.
    """

    def __init__(self):
        log_info_symbol: str = escape(logger.root.handlers[0].get_level_symbol_text(logging.INFO))

        super().__init__(
            TextColumn(
                f"[logging.level.info]{log_info_symbol}[/logging.level.info] "
                "[progress.description]{task.description}",
                justify="right",
            ),
            BarColumn(),
            TaskProgressColumn(
                text_format="[progress.percentage]{task.percentage:>6.2f}%",
                text_format_no_percentage="[progress.percentage]  -.--%",
            ),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            TextColumn("[progress.elapsed](elapsed)"),
            transient=True,
            console=console,
        )

    def start(self) -> None:
        """Start the progress bar and pause running spinners."""
        StackedStatus.pause_stack()
        return super().start()

    def stop(self) -> None:
        """Stop the progress bar and restart paused spinners."""
        res = super().stop()
        StackedStatus.resume_stack()
        return res


class StackedStatus(Status):
    """Status that stacks on top of other statuses.
    Prevent errors about having multiple live displays at once when nesting spinners
    by stopping the previous one when starting a new one, then resuming the previous one after.
    """

    _stack: ClassVar[List[Status]] = []
    """Stack of active statuses."""

    _paused: ClassVar[bool] = False
    """Whether the status stack is paused."""

    def __enter__(self) -> "Status":
        """Start the status and add it to the stack,
        stopping already running statuses.
        """
        if self.stack:
            self.stack[-1].stop()

        self.stack.append(self)
        return super().__enter__()

    def __exit__(self, *args, **kwargs):
        """Remove the status from the stack and restart the previous one."""
        super().__exit__(*args, **kwargs)
        self.stack.pop()

        if self.stack:
            self.stack[-1].start()

    @property
    def stack(self) -> List[Status]:
        """Return the stack of active statuses."""
        return self.__class__._stack

    @classmethod
    def pause_stack(cls):
        """Pause all statuses in the stack.
        Useful for displaying a prompt or logging in between spinners.
        """
        if cls._stack:
            cls._paused = True
            cls._stack[-1].stop()

    @classmethod
    def resume_stack(cls):
        """Resume the last status in the stack.
        Useful for displaying a prompt or logging in between spinners.
        """
        if cls._stack and cls._paused:
            cls._stack[-1].start()
            cls._paused = False


def spinner(message: str):
    """Context manager to display a spinner while executing code.

    :param message: The message to display.
    :type message: str
    """
    status = StackedStatus(repr_console.render_str(message), console=repr_console, spinner="arc")
    status._spinner.frames = [f"[{frame}]" for frame in status._spinner.frames]
    return status
