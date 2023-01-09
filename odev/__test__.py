import os
from signal import SIGINT, SIGTERM, signal

from odev._version import __version__
from odev.common import signal_handling as handlers, odev
from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger = logging.getLogger(__name__)


# --- Main entry method --------------------------------------------------------


def main():
    """Odev initial setup entry point."""
    try:
        _logger.debug(f"Starting setup for odev version {__version__}")

        # --- Handle signals and interrupts ------------------------------------
        for sig in (SIGINT, SIGTERM):
            signal(sig, handlers.signal_handler_exit)

        _logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise Exception("Odev should not be run as root")

        odev.update(ConfigManager("odev"))

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        _logger.exception("Execution failed due to an unhandled exception")
        exit(1)

    _logger.debug("Execution completed successfully")
