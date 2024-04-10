import os
import sys
from signal import SIGINT, SIGTERM, signal


if sys.version_info < (3, 10):
    raise RuntimeError("Odev requires Python 3.10 or later")


import odev.setup as setup
from odev._version import __version__
from odev.common import init_framework, signal_handling as handlers
from odev.common.logging import logging


logger = logging.getLogger(__name__)


# --- Main entry method --------------------------------------------------------


def main():
    """Odev initial setup entry point."""
    try:
        logger.debug(f"Starting setup for odev version {__version__}")

        # --- Handle signals and interrupts ------------------------------------
        for sig in (SIGINT, SIGTERM):
            signal(sig, handlers.signal_handler_exit)

        logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise RuntimeError("Odev should not be run as root")

        # --- Initialize odev configuration files ------------------------------
        logger.debug("Initializing configuration files")
        odev = init_framework()

        # --- Create directories -------------------------------------------
        logger.info("Setting up working directories")
        setup.directories.setup(odev.config)

        # --- Create symlinks ----------------------------------------------
        logger.info("Setting up symlinks for command registration")
        setup.symlink.setup(odev.config)

        # --- Enable autocompletion ----------------------------------------
        logger.info("Setting up autocompletion")
        setup.completion.setup(odev.config)

        # --- Configure self-update ----------------------------------------
        logger.info("Configuring self-update")
        setup.update.setup(odev.config)

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        logger.exception("Execution failed due to an unhandled exception")
        exit(1)

    logger.debug("Execution completed successfully")
