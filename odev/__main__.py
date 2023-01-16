import os
from signal import SIGINT, SIGTERM, signal

from odev._version import __version__
from odev.common import signal_handling as handlers, odev
from odev.common.config import ConfigManager
from odev.common.logging import logging


# Explicitly initialize relative imports if run directly
# if not __package__:
#     package_dir = os.path.dirname(os.path.realpath(__file__))
#     sys.path.append(os.path.normpath(os.path.join(package_dir, "..")))
#     __package__ = os.path.basename(package_dir)  # pylint: disable=redefined-builtin


# from odev.structures.registry import CommandRegistry
# from odev.utils.github import self_update


_logger = logging.getLogger(__name__)


# --- Main entry method --------------------------------------------------------


def main():
    """
    Manages taking input from the user and calling the subsequent subcommands
    with the proper arguments as specified in the command line.
    """
    try:
        _logger.debug(f"Starting odev version {__version__}")

        # --- Handle signals and interrupts ------------------------------------
        for sig in (SIGINT, SIGTERM):
            signal(sig, handlers.signal_handler_exit)

        _logger.debug("Checking runtime permissions")
        if os.geteuid() == 0:
            raise Exception("Odev should not be run as root")

        # --- Update and restart -----------------------------------------------
        if odev.update(ConfigManager("odev")):
            odev.restart()

        # registry = CommandRegistry()
        # registry.run_upgrades()
        # registry.load_commands()
        # registry.handle()

    except KeyboardInterrupt:
        handlers.signal_handler_exit(SIGINT, None)

    except Exception:
        _logger.exception("Execution failed due to an unhandled exception")
        exit(1)

    _logger.debug("Execution completed successfully")
