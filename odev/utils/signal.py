# type: ignore

import signal
from contextlib import contextmanager
from signal import SIGINT, SIGTERM, Signals
from types import FrameType
from typing import (
    Callable,
    Collection,
    MutableMapping,
    Optional,
    Union,
)

from odev.utils import logging


_logger = logging.getLogger(__name__)

SignalHandler = Callable[[Signals, FrameType], None]


def warn_signal_handler(signum: Signals, frame: FrameType) -> None:
    _logger.warning(f"Received signal {signum}")


@contextmanager
def capture_signals(
    signals: Optional[Union[Signals, Collection[Signals]]] = None,
    handler: Optional[SignalHandler] = None,
):
    if isinstance(signals, Signals):
        signals = [signals]

    if signals is None:
        signals = [SIGINT, SIGTERM]

    if handler is None:
        handler = warn_signal_handler

    original_handlers: MutableMapping[Signals, Optional[SignalHandler]] = {}
    signum: Signals

    try:
        for signum in signals:
            original_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, handler)
        yield
    finally:
        original_handler: Optional[SignalHandler]
        for signum, original_handler in original_handlers.items():
            signal.signal(signum, original_handler)
