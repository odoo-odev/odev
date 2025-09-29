from datetime import datetime

from packaging import version

from odev.common import string
from odev.common.commands import Command
from odev.common.config import DATETIME_FORMAT
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class UpdateCommand(Command):
    """Force updating Odev and the currently enabled plugins."""

    _name = "update"
    _aliases = ["u"]

    def run(self):
        from_version = self.config.update.version
        logger.info(f"Current version: {string.stylize(from_version, 'repr.version')}")
        update_mode = self.odev.config.update.mode
        self.odev.config.update.mode = "always"
        self.odev.config.update.date = datetime.strptime("1995-12-21 00:00:00", DATETIME_FORMAT)
        updated = self.odev.update(restart=False, upgrade=True)
        self.odev.config.update.mode = update_mode

        if updated and version.parse(from_version) < version.parse(self.odev.version):
            logger.info(f"Updated to {string.stylize(self.odev.version, 'repr.version')}!")
        else:
            logger.info("Odev is up to date")
