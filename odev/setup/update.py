"""Configure self-update behavior."""

from odev.common.console import console
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


PRIORITY = 40


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Configure self-update behavior.

    :param config: Configuration manager
    """
    update_mode = console.select(
        "What should happen when a new version of odev becomes available?",
        default=odev.config.update.mode,
        choices=[
            ("always", "Update odev automatically"),
            ("never", "Never update odev"),
            ("ask", "Ask me before updating odev"),
        ],
    )

    if update_mode is not None:
        odev.config.update.mode = update_mode

    update_interval = console.integer(
        "How often should odev check for updates (in days)?",
        default=odev.config.update.interval,
        min_value=1,
    )

    if update_interval is not None:
        odev.config.update.interval = update_interval
