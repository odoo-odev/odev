"""Upgrade to odev 4.18.0.

Warn the user about reinstallation needed for executing
"""

from odev.common.bash import execute
from odev.common.logging import logging
from odev.common.odev import Odev
from odev.common.string import stylize


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:
    logger.warning("This upgrade requires reinstallation of odev to switch to using a dedicated virtual environment")
    logger.info("This is required for using odev on Ubuntu 24.04 and later")
    logger.info(f"The reinstallation will be done automatically for you {stylize('now', 'bold cyan')}")
    execute(f"cd {odev.path} && ./install.sh")
    logger.info("Done! You can now continue using odev as before")
