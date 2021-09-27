'''Kills a running Odoo database.'''

import os

from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class KillCommand(commands.LocalDatabaseCommand):
    '''
    Kill a running Odoo database. Useful if the process crashed because of
    a forgotten IPDB or if you lost your terminal and don't want to search
    for the process' PID.
    '''

    name = 'kill'

    def run(self):
        '''
        Kills the process of a running local database.
        '''

        self.check_database()
        self.ensure_running()

        _logger.info(f'Stopping database {self.database}')
        pid = self.db_pid()

        while pid:
            os.system(f'kill -9 {pid}')
            pid = self.db_pid()

        return 0
