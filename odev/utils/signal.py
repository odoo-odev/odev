# -*- coding: utf-8 -*-

import signal
from signal import Signals, SIGINT, SIGTERM
from contextlib import contextmanager
from types import FrameType
from typing import (
    Callable,
    ContextManager,
    Union,
    Collection,
    Optional,
    MutableMapping,
)

from odev.utils import logging


logger = logging.getLogger(__name__)

SignalHandler = Callable[[Signals, FrameType], None]


def warn_signal_handler(signum: Signals, frame: FrameType) -> None:
    logger.warning(f'Received signal {signum}')


@contextmanager
def capture_signals(
    signals: Optional[Union[Signals, Collection[Signals]]] = None,
    handler: Optional[SignalHandler] = None,
) -> ContextManager:
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
