"""Upgrade to odev 4.0.0"""

from datetime import datetime
from pathlib import Path

from odev._version import __version__
from odev.common.config import Config
from odev.constants import DEFAULT_DATETIME_FORMAT


def run(config: Config) -> None:

    # --- Update config file ---------------------------------------------------

    check_date_value: str = config._config.get("update", "last_check", "")

    if check_date_value:
        check_date = datetime.strptime(check_date_value, DEFAULT_DATETIME_FORMAT)
    else:
        check_date = datetime.utcnow()

    check_interval = config._config.get("update", "check_interval", "1")
    version = config._config.get("odev", "version", __version__)

    config.update.date = check_date
    config.update.interval = int(check_interval)
    config.update.version = version
    config.update.mode = "ask"

    config._config.delete("update", "last_check")
    config._config.delete("update", "check_interval")

    config.paths.repositories = Path(config._config.get("paths", "custom", "~/odoo/repositories"))
    config.paths.dumps = config.paths.repositories.parent / "dumps"
    config._config.delete("paths", "standard")
    config._config.delete("paths", "custom")
    config._config.delete("paths", "odev")
    config._config.delete("paths", "odoo")
    config._config.delete("paths", "dump")
    config._config.delete("paths", "dev")

    config._config.delete("odev")
    config._config.delete("cleaning")
    config._config.delete("repos")
