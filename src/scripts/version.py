# -*- coding: utf-8 -*-

from . import script
from .. import utils


class VersionScript(script.Script):

    usage = 'version <database>'
    alias = ['v']
    args = [['database', 'Database to get the Odoo version of']]
    description = """
Gets the version of a local Odoo database.
"""

    def run(self, database, options):
        """
        Gets the Odoo version of a local database.
        """

        self.db_is_valid(database)

        utils.log('info', 'Database \'%s\' runs %s' % (database, self.db_version_full(database)))

        return 0
