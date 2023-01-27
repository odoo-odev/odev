"""Catch OS signals and interrupts to handle them gracefully."""

from contextlib import contextmanager
from signal import (
    SIGINT,
    SIGTERM,
    Handlers,
    Signals,
    getsignal,
    signal,
)
from types import FrameType
from typing import (
    Any,
    Callable,
    Collection,
    MutableMapping,
    Optional,
    Union,
)

from odev.common import prompt
from odev.common.logging import logging


__all__ = ["signal_handler_warning", "signal_handler_exit"]


logger = logging.getLogger(__name__)


# --- Handle signals and interrupts --------------------------------------------


def signal_handler_warning(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
    """Log a warning message with the signal received."""
    prompt.clear_line(0)  # Hide control characters
    logger.warning(message or f"Received signal ({signal_number})")


def signal_handler_exit(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
    """Log a warning message with the signal received and exit the current process."""
    signal_handler_warning(
        signal_number=signal_number,
        frame=frame,
        message=message or f"Received signal ({signal_number}), aborting execution",
    )
    exit(signal_number)


def signal_handler_subprocess(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
    """Send over the signal to a subprocess when using :func:`capture_signals` or do nothing."""


# --- Context manager to handle signals on a specific block --------------------


SignalHandler = Union[Callable[[Union[int, Signals], Optional[FrameType]], Any], int, Handlers, None]


@contextmanager
def capture_signals(
    signals: Optional[Union[Signals, Collection[Signals]]] = None,
    handler: Optional[SignalHandler] = None,
):
    """Capture OS signals and interrupts and handle them gracefully.

    :param list signals: The signals to capture.
    :param callable handler: The handler to use for the signals.
    """
    if signals is None:
        signals = [SIGINT, SIGTERM]
    elif isinstance(signals, Signals):
        signals = [signals]

    if handler is None:
        handler = signal_handler_subprocess

    original_handlers: MutableMapping[Signals, Optional[SignalHandler]] = {}

    try:
        for signal_number in signals:
            original_handlers[signal_number] = getsignal(signal_number)
            signal(signal_number, handler)

        yield

    finally:
        for signal_number, original_handler in original_handlers.items():
            signal(signal_number, original_handler)
