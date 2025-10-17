import os
import pkgutil
import sys
from importlib import import_module
from importlib.util import find_spec
from signal import SIGINT, SIGTERM, signal

from odev._version import __version__
from odev.common import init_framework, signal_handling as handlers
from odev.common.errors import OdevError
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

        # --- Do not run as superuser ------------------------------------------
        logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise OdevError("Odev should not be run as root")

        # --- Initialize odev configuration files ------------------------------
        logger.debug("Initializing configuration files")
        odev = init_framework()

        # --- Load and run setup modules ---------------------------------------
        loader = find_spec("odev.setup")

        if loader is None or not loader.submodule_search_locations:
            raise OdevError("Could not find the setup module")

        submodules = sorted(
            (
                import_module(f"{loader.name}.{submodule_info.name}")
                for submodule_info in pkgutil.iter_modules(loader.submodule_search_locations)
            ),
            key=lambda submodule: getattr(submodule, "PRIORITY", 0),
        )

        for submodule in submodules:
            if hasattr(submodule, "setup"):
                if hasattr(submodule, "__doc__") and submodule.__doc__ is not None:
                    logger.info(submodule.__doc__.strip())
                submodule.setup(odev)

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        logger.exception("Execution failed due to an unhandled exception")
        sys.exit(1)

    logger.debug("Execution completed successfully")
