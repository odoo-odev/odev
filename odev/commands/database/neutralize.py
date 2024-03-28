from odev.common.commands import LocalDatabaseCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class NeutralizeCommand(LocalDatabaseCommand):
    """Neutralize a local database and make it suitable for development without risking sending emails or running
    undesired actions.
    """

    _name = "neutralize"
    _aliases = ["clean", "cl"]

    def run(self):
        self._database.neutralize()
        logger.info(
            f"""
            Database {self._database.name!r} has been neutralized and is now safe to use for development
            - Login to the administrator account with the credentials 'admin:admin'
            - Login to other users with their login and the password 'odoo'
            - Scheduled actions have been deactivated
            - Website domains have been cleared
            - Outgoing mail servers have been disabled and a new one has been added to 'localhost:1025'
              You can access outgoing emails using a local SMTP server like https://github.com/mailhog/MailHog
              or https://rubygems.org/gems/mailcatcher
            """
        )
