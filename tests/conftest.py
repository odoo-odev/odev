"""Session-wide setup for the test suite: give this run a private sandbox and make sure it is cleaned up.

`pytest_sessionfinish` runs from a `finally` block in pytest's session wrapper, so the sandbox is removed
both when the suite completes and when it is interrupted. A `SIGTERM` and a `Ctrl+C` are both turned into
the same orderly exit, and anything that still escapes — a `SIGKILL`, a crashed interpreter — is picked up
by the sweep at the start of the next run.
"""

import atexit
from collections.abc import Callable
from signal import SIGINT, SIGTERM, Signals, signal
from typing import Any
from unittest.mock import patch

import pytest

from tests.fixtures import sandbox


TERMINATED_EXIT_CODE = 2
"""Exit code reported when the suite is stopped before it could complete."""

INTERRUPT_MESSAGE = "interrupted"
"""Reason reported when the suite is stopped before it could complete."""

SIGNAL_INSTALLER = "odev.common.signal_handling.signal"
"""Where odev installs the signal handlers it uses to cancel the operation it is running."""


class InterruptRecorder:
    """Signal handler noting an interrupt for the session, then handing it over to odev.

    odev captures `SIGINT` around every query and every subprocess, and its handlers cancel that single
    operation instead of propagating. A suite spends much of its time inside one of those blocks, so a
    `Ctrl+C` landing in one would be swallowed and the run would carry on. Letting the interrupt through
    instead abandons the PostgreSQL connection mid-statement, and a suite interrupted that way exhausts
    the connection slots of the server; so it is recorded here and acted upon at the next test boundary,
    once odev has closed what it had open.
    """

    interrupted: bool = False
    """Whether an interrupt was received while odev was holding the signal handlers."""

    def __init__(self, handler: Callable[..., Any]):
        self.handler: Callable[..., Any] = handler
        """The handler odev installed, called once the interrupt has been recorded."""

    def __call__(self, *args) -> Any:
        InterruptRecorder.interrupted = True

        return self.handler(*args)


def pytest_configure(config: pytest.Config) -> None:
    """Make the suite stoppable, whichever way it is asked to stop."""

    def terminate(*args):
        pytest.exit(INTERRUPT_MESSAGE, returncode=TERMINATED_EXIT_CODE)

    signal(SIGTERM, terminate)

    installer = patch(SIGNAL_INSTALLER, new=install_handler)
    installer.start()
    config.add_cleanup(installer.stop)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Claim a sandbox for this run, then clean up after the runs that no longer own theirs."""
    sandbox.acquire()
    atexit.register(sandbox.release)
    sandbox.sweep()


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Stop the session on an interrupt odev handled itself, now that it is between two tests."""
    if InterruptRecorder.interrupted:
        pytest.exit(INTERRUPT_MESSAGE, returncode=TERMINATED_EXIT_CODE)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove the sandbox of this run, whether the suite completed or was interrupted."""
    sandbox.release()


def install_handler(signal_number: Signals, handler: Any) -> Any:
    """Install a signal handler for odev, recording the interrupts it would otherwise swallow.

    :param signal_number: The signal odev wants to handle.
    :param handler: The handler it wants to install, or the one it restores once its block is over.
    :return: The handler that was previously installed.
    """
    if signal_number != SIGINT or not callable(handler) or isinstance(handler, InterruptRecorder):
        return signal(signal_number, handler)

    return signal(signal_number, InterruptRecorder(handler))
