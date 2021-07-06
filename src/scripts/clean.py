# -*- coding: utf-8 -*-

from . import script
from .. import utils


class CleanScript(script.Script):

    usage = 'clean <database>'
    args = [['database', 'Name of the local database to clean']]
    description = """
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
        # "UPDATE auth_oauth_provider SET enabled = false",
    ]

    def run(self, database, options):
        """
        Cleans a database and make it suitable for development and testing locally.
        """

        self.ensure_stopped(database)

        utils.log('info', 'Cleaning database %s' % (database))
        result = super().run(database, self.queries)

        if not result:
            return 1

        self.db_config(database, [('clean', 'True')])

        utils.log('info', 'Cleaned database %s' % (database))
        utils.log('info', 'Login to the administrator account with the credentials \'admin:admin\'')
        utils.log('info', 'Login to any other account with their email address and the password \'odoo\'')
        return 0
