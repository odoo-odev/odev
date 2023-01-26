import os
from signal import SIGINT, SIGTERM, signal
from time import monotonic

from odev._version import __version__
from odev.common import signal_handling as handlers
from odev.common.config import ConfigManager
from odev.common.logging import logging
from odev.common.odev import Odev


_logger = logging.getLogger(__name__)


# --- Main entry method --------------------------------------------------------


def main():
    """
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    """
    start_time = monotonic()

    try:
        _logger.debug(f"Starting odev version {__version__}")

        # --- Handle signals and interrupts ------------------------------------
        for sig in (SIGINT, SIGTERM):
            signal(sig, handlers.signal_handler_exit)

        _logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise Exception("Odev should not be run as root")

        with ConfigManager("odev") as config:
            Odev(config).dispatch()

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        _logger.exception("Execution failed due to an unhandled exception")
        exit(1)

    _logger.debug(f"Execution completed successfully in {monotonic() - start_time:.3f} seconds")
