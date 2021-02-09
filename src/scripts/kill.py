# -*- coding: utf-8 -*-

import os

from . import script
from .. import utils


class KillScript(script.Script):

    usage = 'kill <database>'
    args = [['database', 'Name of the local database to kill the process of']]
    description = """
Kills a running Odoo database. Useful if the process crashed because of
a forgotten IPDB or if you lost your terminal and don't want to search
for the process' PID.
"""

    def run(self, database, options):
        """
        Kills the process of a running local database.
        """

        self.db_is_valid(database)
        self.ensure_running(database)

        utils.log('info', 'Stopping database %s' % (database))
        pid = self.db_pid(database)

        while pid:
            os.system('kill -9 %s' % (pid))
            pid = self.db_pid(database)

        return 0
