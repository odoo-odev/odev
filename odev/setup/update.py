"""Configure self-update behavior."""

from datetime import datetime

from odev._version import __version__
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

    update_interval = console.integer(
        "How often should odev check for updates (in days)?",
        default=config.update.interval,
        min_value=1,
    )

    config.update.mode = update_mode
    config.update.interval = update_interval
    config.update.date = datetime.utcnow()
    config.update.version = __version__
