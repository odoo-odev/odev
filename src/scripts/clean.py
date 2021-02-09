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
- Set password for all other users to odoo
- Extend database validity to December 2050
"""

    queries = [
        "UPDATE res_users SET login='admin',password='admin' WHERE id IN (SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 1)",
        "UPDATE res_users SET password='odoo' WHERE login != 'admin' AND password IS NOT NULL",
        "UPDATE ir_config_parameter SET value='2050-12-12' WHERE key='database.expiration_date'",
        "UPDATE ir_config_parameter SET value='http://localhost:8069' WHERE key='web.base.url'",
        "UPDATE ir_cron SET active='False'",
        "DELETE FROM fetchmail_server",
        "DELETE FROM ir_mail_server",
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
