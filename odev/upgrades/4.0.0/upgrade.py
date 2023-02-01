"""Upgrade to odev 4.0.0"""

from datetime import datetime

from odev._version import __version__
from odev.common.config import ConfigManager
from odev.constants import DEFAULT_DATETIME_FORMAT


def run(config: ConfigManager) -> None:

    # --- Update config file ---------------------------------------------------

    check_date = config.get("update", "last_check", datetime.now().strftime(DEFAULT_DATETIME_FORMAT))
    check_interval = config.get("update", "check_interval", 1)
    version = config.get("odev", "version", __version__)

    config.set("update", "date", check_date)
    config.set("update", "interval", check_interval)
    config.set("update", "version", version)
    config.set("update", "mode", "ask")

    config.delete("update", "last_check")
    config.delete("update", "check_interval")
    config.delete("odev")

    config.set("paths", "repositories", config.get("paths", "custom", "~/odoo/repositories"))
    config.delete("paths", "standard")
    config.delete("paths", "custom")
