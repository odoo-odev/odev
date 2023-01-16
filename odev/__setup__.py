import os
from signal import SIGINT, SIGTERM, signal

import odev.setup as setup
from odev._version import __version__
from odev.common import signal_handling as handlers
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

        # --- Initialize odev configuration files ------------------------------
        _logger.debug("Initializing configuration files")

        with ConfigManager("odev") as config:

            # --- Create directories -------------------------------------------
            _logger.info("Setting up working directories")
            setup.directories.setup(config)

            # --- Create symlinks ----------------------------------------------
            _logger.info("Setting up symlinks for command registration")
            setup.symlink.setup(config)

            # --- Enable autocompletion ----------------------------------------
            _logger.info("Setting up autocompletion")
            setup.completion.setup(config)

            # --- Configure self-update ----------------------------------------
            _logger.info("Configuring self-update")
            setup.update.setup(config)

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        _logger.exception("Execution failed due to an unhandled exception")
        exit(1)

    _logger.debug("Execution completed successfully")
