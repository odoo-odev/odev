from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class NeutralizeCommand(DatabaseCommand):
    """Neutralize a local database and make it suitable for development."""

    name = "neutralize"
    aliases = ["clean", "cl"]
    database: LocalDatabase

    _database_allowed_platforms = ["local"]

    def run(self):
        self.database.neutralize()
        logger.info(
            f"""
            Database {self.database.name!r} has been neutralized and is now safe to use for development
            - Login to the administrator account with the credentials 'admin:admin'
            - Login to other users with their login and the password 'odoo'
            - Scheduled actions have been deactivated
            - Website domains have been cleared
            - Outgoing mail servers have been disabled and a new one has been added to 'localhost:1025'
              You can access outgoing emails using a local SMTP server like https://github.com/mailhog/MailHog
              or https://rubygems.org/gems/mailcatcher
            """
        )
