"""Makes a local Odoo database suitable for development."""

import logging

from .database import LocalDBCommand


_logger = logging.getLogger(__name__)


class CleanScript(LocalDBCommand):
    command = "clean"
    help = """
        Makes a local Odoo database suitable for development:
        - Disables automated and scheduled actions
        - Disables mails
        - Set credentials for Administrator user to admin:admin
        - Set password for first 50 users to odoo
        - Extend database validity to December 2050 and remove enterprise code
        - Set report.url and web.base.url to http://localhost:8069
    """

    queries = [
        "UPDATE res_users SET login='admin',password='admin' WHERE id IN (SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 1)",
        "UPDATE res_users SET password='odoo' WHERE login != 'admin' AND password IS NOT NULL AND id IN (SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 50)",
        "UPDATE ir_config_parameter SET value='2050-12-12' WHERE key='database.expiration_date'",
        "DELETE FROM ir_config_parameter where key ='database.enterprise_code'",
        "UPDATE ir_config_parameter SET value='http://localhost:8069' WHERE key='web.base.url'",
        "UPDATE ir_config_parameter SET value='http://localhost:8069' WHERE key='report.url'",
        "UPDATE ir_cron SET active='False'",
        "DELETE FROM fetchmail_server",
        "DELETE FROM ir_mail_server",
        "UPDATE auth_oauth_provider SET enabled = false",
    ]

    def run(self):
        """
        Cleans a database and make it suitable for development and testing locally.
        """

        self.ensure_stopped()

        _logger.info(f'Cleaning database {self.database}')
        result = self.run_queries(self.queries)

        if not result:
            return 1

        self.db_config(clean='True')

        _logger.info(f'Cleaned database {self.database}')
        _logger.info('Login to the administrator account with the credentials \'admin:admin\'')
        _logger.info('Login to any other account with their email address and the password \'odoo\'')
        return 0
