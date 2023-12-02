"""Upgrade to odev 4.0.0"""

from pathlib import Path

from odev._version import __version__
from odev.common.config import Config


def run(config: Config) -> None:

    # --- Update config file ---------------------------------------------------

    interval = config.parser.get("update", "check_interval", fallback="1")
    version = config.parser.get("odev", "version", fallback=__version__)
    config.reset("update")
    config.update.interval = int(interval)
    config.update.version = version

    repositories = config.parser.get("paths", "repositories", fallback="~/odoo/repositories")
    dumps = config.parser.get("paths", "dumps", fallback="~/odoo/dumps")
    config.reset("paths")
    config.paths.repositories = Path(repositories).expanduser()
    config.paths.dumps = Path(dumps).expanduser()

    config.delete("odev")
    config.delete("cleaning")
    config.delete("repos")
