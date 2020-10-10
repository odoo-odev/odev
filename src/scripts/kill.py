# -*- coding: utf-8 -*-

import os

from . import script
from .. import utils


class KillScript(script.Script):

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
