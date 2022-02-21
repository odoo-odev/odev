import math
import random
import time
from collections import defaultdict
from contextlib import ExitStack
from typing import List, Mapping, Optional, Union

import enlighten

from odev.utils.logging import term


def poll_loop(poll_interval: float):
    while True:
        time.sleep(poll_interval)
        yield


class SpinnerBar:
    def __init__(self, message: Optional[str] = None):
        br_start: int = ord("\u2800")
        br_end: int = ord("\u28ff")
        self._density_bins: Mapping[int, List[str]] = defaultdict(list)
        for o in range(br_start, br_end):
            self._density_bins[bin(o - br_start).count("1")].append(chr(o))
        self._density_bins = dict(self._density_bins)
        self._db_max: int = max(self._density_bins.keys())
        self._message: Optional[str] = message
        self._manager: Union[enlighten.Manager, enlighten.NotebookManager] = enlighten.get_manager()
        self._status_bar: enlighten.StatusBar = self._manager.status_bar(
            "",
            color="white_on_deeppink4",
            justify=enlighten.Justify.CENTER,
            leave=False,
        )
        self._exit_stack: ExitStack = ExitStack()

    def __enter__(self):
        self._exit_stack.enter_context(self._manager)
        self._exit_stack.enter_context(self._status_bar)
        return self

    @property
    def message(self) -> Optional[str]:
        return self._message

    @message.setter
    def message(self, value: Optional[str]) -> None:
        self._message = value

    def update(self, pos: Optional[float] = None):
        padded_message: str = f" {self._message} " if self.message else ""
        bar_width: int = term.width - len(padded_message)
        if pos is None:
            pos = (-time.monotonic() * 40) / bar_width
        intensities: List[float] = [
            (0.5 - 0.5 * math.cos((max(0.0, min(-1 + 2 * pos + p, 1.0)) + 1) * 2 * math.pi))
            * math.sin(p * math.pi) ** 0.5
            for i in range(bar_width)
            if (p := (i / bar_width)) is not None
        ]
        bar_str: str = "".join(
            random.choice(self._density_bins[int((self._db_max + 0.99999) * max(0.0, min(i, 1.0)))])
            for i in intensities
        )
        status_str: str = padded_message + bar_str[::-1]
        self._status_bar.update(status_str)
        self._status_bar.refresh()

    def loop(self, poll_interval: float, spinner_fps: float = 20):
        spinner_interval: float = 1 / spinner_fps
        tick: float = time.monotonic()
        try:
            while True:
                time.sleep(spinner_interval)
                since_last_tick: float = time.monotonic() - tick
                duration: float = max(1.0, poll_interval / max(1, int(poll_interval / 2.5)))
                pos: float = (since_last_tick / duration) % 1.0
                self.update(pos=pos)
                if since_last_tick < poll_interval:
                    continue
                tick = time.monotonic()
                yield
        except StopIteration:
            return

    def __exit__(self, *exc_args):
        self._exit_stack.close()
        self._status_bar.__exit__(*exc_args)
        self._manager.__exit__(*exc_args)
