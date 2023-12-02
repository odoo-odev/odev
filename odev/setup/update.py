"""Configure self-update behavior."""

from odev.common.config import Config
from odev.common.console import console
from odev.common.logging import logging


logger = logging.getLogger(__name__)


# --- Setup --------------------------------------------------------------------


def setup(config: Config) -> None:
    """Configure self-update behavior.

    :param config: Configuration manager
    """
    update_mode = console.select(
        "What should happen when a new version of odev becomes available?",
        default=config.update.mode,
        choices=[
            ("always", "Update odev automatically"),
            ("never", "Never update odev"),
            ("ask", "Ask me before updating odev"),
        ],
    )

    if update_mode is not None:
        config.update.mode = update_mode

    update_interval = console.integer(
        "How often should odev check for updates (in days)?",
        default=config.update.interval,
        min_value=1,
    )

    if update_interval is not None:
        config.update.interval = update_interval
