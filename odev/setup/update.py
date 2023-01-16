"""Configure self-update behavior."""

from datetime import datetime
from typing import Optional

from odev.constants import DEFAULT_DATETIME_FORMAT
from odev.common import prompt
from odev.common.logging import logging
from odev.common.config import ConfigManager


logger = logging.getLogger(__name__)


# --- Setup --------------------------------------------------------------------


def setup(config: Optional[ConfigManager] = None) -> None:
    """Configure self-update behavior.

    :param config: Configuration manager
    """
    update_mode = prompt.select(
        "What should happen when a new version of odev becomes available?",
        default="always",
        choices=[
            ("always", "Update odev automatically"),
            ("never", "Never update odev"),
            ("ask", "Ask me before updating odev"),
        ],
    )

    update_interval = prompt.integer("How often should odev check for updates (in days)?", default=1, min_value=1)

    config.set("update", "mode", update_mode)
    config.set("update", "interval", update_interval)
    config.set("update", "date", datetime.now().strftime(DEFAULT_DATETIME_FORMAT))
