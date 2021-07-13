"""Gets the version of a local Odoo database."""

import logging

from .database import LocalDBCommand


_logger = logging.getLogger(__name__)


class VersionScript(LocalDBCommand):
    command = "version"
    aliases = ("v",)
    help = "Gets the version of a local Odoo database."

    def run(self):
        """
        Gets the Odoo version of a local database.
        """

        self.db_is_valid()

        version = self.db_version_full()
        _logger.info(f'Database "{self.database}" runs {version}')

        return 0
