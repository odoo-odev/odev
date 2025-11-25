import os
import sys
from bdb import BdbQuit
from signal import SIGINT, SIGTERM, signal
from time import monotonic


# --- Main entry method --------------------------------------------------------


def main():
    """Manage taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    """
    start_time = monotonic()

    # --- Dynamically import odev to include startup time in performance stats -
    from odev.common import init_framework, signal_handling as handlers  # noqa: PLC0415
    from odev.common.errors.odev import OdevError  # noqa: PLC0415
    from odev.common.logging import logging  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    logger.debug(f"Framework loaded in {monotonic() - start_time:.3f} seconds")

    try:
        # --- Handle signals and interrupts ------------------------------------
        for sig in (SIGINT, SIGTERM):
            signal(sig, handlers.signal_handler_exit)

        logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise OdevError("Odev should not be run as root")

        odev = init_framework()
        odev.start(start_time)
        logger.debug(f"Framework started in {monotonic() - start_time:.3f} seconds")
        odev.dispatch()

    except OdevError as error:
        logger.error(error)
        sys.exit(1)

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except BdbQuit:
        logger.error("Debugger execution interrupted")
        sys.exit(1)

    except Exception:
        logger.exception("Execution failed due to an unhandled exception")
        sys.exit(1)

    logger.debug(f"Execution completed successfully in {monotonic() - start_time:.3f} seconds")
