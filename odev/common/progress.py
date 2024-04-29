"""Statuses list to keep track of all active spinners and prevent them from being
stacked on top of each other.
"""

from typing import ClassVar, List, Optional

from rich.console import RenderableType
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress as RichProgress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.status import Status
from rich.style import StyleType

from odev.common import string
from odev.common.console import console
from odev.common.debug import DEBUG_MODE
from odev.common.logging import OdevRichHandler, logging


__all__ = ["Progress", "StackedStatus", "spinner"]


logger = logging.getLogger(__name__)


if DEBUG_MODE:
    logger.warning(
        "Disabling live status due to debugger usage:\n"
        + string.join_bullet(["Progress bars will not be shown", "Spinners will be replaced with log messages"])
    )


class Progress(RichProgress):
    """Progress bar that displays the log level symbol on the left.
    Also pauses running spinners when starting the progress bar to avoid errors about
    having multiple live displays at once.
    """

    def __init__(self, download: bool = False):
        handler = next(
            filter(lambda handler: isinstance(handler, OdevRichHandler), logger.root.handlers),
            OdevRichHandler(console=console),
        )
        assert isinstance(handler, OdevRichHandler)
        log_info_symbol: str = escape(handler.get_level_symbol_text(logging.INFO))

        columns = [
            TextColumn(
                f"[logging.level.info]{log_info_symbol}[/logging.level.info] "
                "[progress.description]{task.description}",
            ),
            BarColumn(),
            TaskProgressColumn(
                text_format="[progress.percentage]{task.percentage:>6.2f}%",
                text_format_no_percentage="[progress.percentage]  -.--%",
            ),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            TextColumn("[progress.elapsed](elapsed)"),
        ]

        if download:
            columns.append(DownloadColumn())

        super().__init__(
            *columns,
            transient=True,
            console=console,
        )

    def start(self) -> None:
        """Start the progress bar and pause running spinners."""
        StackedStatus.pause_stack()
        console.is_live = True
        return super().start()

    def stop(self) -> None:
        """Stop the progress bar and restart paused spinners."""
        res = super().stop()
        StackedStatus.resume_stack()
        console.is_live = False
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

        if DEBUG_MODE:
            return self

        console.is_live = True
        self.stack.append(self)
        return super().__enter__()

    def __exit__(self, *args, **kwargs):
        """Remove the status from the stack and restart the previous one."""
        super().__exit__(*args, **kwargs)

        if self.stack:
            self.stack.pop()

        if self.stack:
            self.stack[-1].start()
        else:
            console.is_live = False

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
            console.is_live = False
            cls._paused = True
            cls._stack[-1].stop()

    @classmethod
    def resume_stack(cls):
        """Resume the last status in the stack.
        Useful for displaying a prompt or logging in between spinners.
        """
        if cls._stack and cls._paused:
            console.is_live = True
            cls._stack[-1].start()
            cls._paused = False

    def update(
        self,
        status: Optional[RenderableType] = None,
        *,
        spinner: Optional[str] = None,
        spinner_style: Optional[StyleType] = None,
        speed: Optional[float] = None,
    ) -> None:
        if status is not None:
            if isinstance(status, str):
                status = string.normalize_indent(status)
                status = console.render_str(status)

        return super().update(status, spinner=spinner, spinner_style=spinner_style, speed=speed)


def spinner(message: str) -> StackedStatus:
    """Context manager to display a spinner while executing code.

    :param message: The message to display.
    :type message: str
    """
    if DEBUG_MODE:
        logger.info(message)

    status = StackedStatus(console.render_str(message), console=console, spinner="arc")
    status._spinner.frames = [f"[{frame}]" for frame in status._spinner.frames]
    return status
