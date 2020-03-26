# -*- coding: utf-8 -*-

from . import script
from .. import utils


class CleanScript(script.Script):

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

        self.db_valid(database)

        if self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

        utils.log('info', 'Preparing database %s' % (database))
        result = super().run(database, self.queries)
        
        if not result:
            return 1
        
        utils.log('info', 'Prepared database %s' % (database))
        return 0
