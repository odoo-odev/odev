from datetime import datetime

from odev.common.commands import Command
from odev.common.config import DATETIME_FORMAT
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class UpdateCommand(Command):
    """Force updating Odev and the currently enabled plugins."""

    _name = "update"
    _aliases = ["upgrade", "u"]

    def run(self):
        logger.info(f"Current version: [repr.version]{self.config.update.version}[/repr.version]")
        update_mode = self.odev.config.update.mode
        self.odev.config.update.mode = "always"
        self.odev.config.update.date = datetime.strptime("1995-12-21 00:00:00", DATETIME_FORMAT)
        self.odev._update(restart=False)
        self.odev.config.update.mode = update_mode

        if self.config.update.version != self.odev.version:
            logger.info(f"Updated to [repr.version]{self.odev.version}[/repr.version]!")
        else:
            logger.info("No update available")
