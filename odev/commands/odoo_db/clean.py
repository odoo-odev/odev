'''Make a local Odoo database suitable for development.'''

from argparse import Namespace

from odev.structures import commands
from odev.utils import logging
from odev.exceptions import InvalidQuery


logger = logging.getLogger(__name__)


class CleanCommand(commands.LocalDatabaseCommand):
    '''
    Render a local Odoo database suitable for development:
      - Disable automated and scheduled actions
      - Disable mails
      - Set credentials for Administrator user to admin:admin
      - Set password for the first 50 users to odoo
      - Extend database validity to December 2050 and remove enterprise code
      - Set report.url and web.base.url to http://localhost:8069
      - Disable Oauth providers
    '''

    name = 'clean'
    aliases = ['cl']
    queries = [
        '''
        UPDATE res_users SET login='admin',password='admin'
        WHERE id IN (SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 1)
        ''',
        '''
        UPDATE res_users SET password='odoo'
        WHERE login != 'admin' AND password IS NOT NULL AND id IN (
            SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 50
        )
        ''',
        'DELETE FROM ir_config_parameter where key =\'database.enterprise_code\'',
        'UPDATE ir_config_parameter SET value=\'http://localhost:8069\' WHERE key=\'web.base.url\'',
        'UPDATE ir_config_parameter SET value=\'http://localhost:8069\' WHERE key=\'report.url\'',
        'UPDATE ir_cron SET active=\'False\'',
        'DELETE FROM fetchmail_server',
        'DELETE FROM ir_mail_server',
        'DO $$ BEGIN IF (EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES  WHERE TABLE_NAME = \'auth_oauth_provider\')) '
        'THEN UPDATE auth_oauth_provider SET enabled = false; END IF; END; $$',
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        expiration_date = '2050-12-12'

        # The database expiration date became a datetime object in version 15.0,
        # as opposed to a date object in previous versions
        if float(self.db_version_clean()) >= 15.0:
            expiration_date += ' 00:00:00'

        self.queries.append(
            f'UPDATE ir_config_parameter SET value=\'{expiration_date}\' WHERE key=\'database.expiration_date\'',
        )

    def run(self):
        '''
        Cleans a database and make it suitable for development and testing locally.
        '''

        self.ensure_stopped()

        logger.info(f'Cleaning database {self.database}')
        result = self.run_queries(self.queries)

        if not result:
            raise InvalidQuery(f'An error occurred while cleaning up database {self.database}')

        self.config['databases'].set(self.database, 'clean', True)

        logger.info('Login to the administrator account with the credentials \'admin:admin\'')
        logger.info('Login to any other account with their email address and the password \'odoo\'')

        return 0
