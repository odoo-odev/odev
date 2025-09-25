"""Upgrade to odev 4.0.0."""

from pathlib import Path

from odev._version import __version__
from odev.common.odev import Odev


def run(odev: Odev) -> None:
    # --- Update config file ---------------------------------------------------

    interval = odev.config.parser.get("update", "check_interval", fallback="1")
    version = odev.config.parser.get("odev", "version", fallback=__version__)
    odev.config.reset("update")
    odev.config.update.interval = int(interval)
    odev.config.update.version = version

    repositories = odev.config.parser.get("paths", "repositories", fallback="~/odoo/repositories")
    dumps = odev.config.parser.get("paths", "dumps", fallback="~/odoo/dumps")
    odev.config.reset("paths")
    odev.config.paths.repositories = Path(repositories).expanduser()
    odev.config.paths.dumps = Path(dumps).expanduser()

    odev.config.delete("odev")
    odev.config.delete("cleaning")
    odev.config.delete("repos")
