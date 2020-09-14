# -*- coding: utf-8 -*-

from . import script
from .. import utils


class CreateScript(script.Script):
    
    def run(self, database, options):
        """
        Creates a new, empty database locally.
        """

        if self.db_exists_all(database):
            message = 'but is not an Odoo database'
            
            if self.db_exists(database):
                message = 'and is an Odoo database'

            raise Exception('Database %s already exists %s' % (database, message))

        utils.log('info', 'Creating database %s' % (database))
        query = 'CREATE DATABASE %s;' % (database)
        result = super().run(self.database, query)

        if not result or not self.db_exists_all(database):
            return 1

        utils.log('info', 'Created database %s' % (database))
        return 0
