"""Upgrade to odev 4.18.0.

Warn the user about reinstallation needed for executing
"""

from odev.common.logging import logging
from odev.common.odev import Odev
from odev.setup import telemetry


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:
    telemetry.setup(odev)
