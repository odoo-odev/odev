"""Gets the version of a local Odoo database."""

from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class VersionCommand(commands.LocalDatabaseCommand):
    """
    Get the Odoo version on which a local database is running.
    """

    name = "version"
    aliases = ["v"]

    def run(self):
        """
        Gets the Odoo version of a local database.
        """

        self.check_database()

        version = self.db_version_full()
        _logger.info(f"Database `{self.database}` runs {version}")

        return 0
