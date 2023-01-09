"""Catch OS signals and interrupts to handle them gracefully."""

from types import FrameType
from typing import Optional

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
