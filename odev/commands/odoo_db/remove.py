'''Removes a local database from PostgreSQL and deletes its filestore.'''

import os
import shutil

from odev.structures import commands
from odev.utils import logging
from odev.constants import DEFAULT_DATABASE
from odev.exceptions import InvalidDatabase, RunningOdooDatabase, CommandAborted


_logger = logging.getLogger(__name__)


class RemoveCommand(commands.LocalDatabaseCommand):
    '''
    Drop a local database in PostgreSQL and delete its Odoo filestore on disk.
    '''

    name = 'remove'
    aliases = ['rm', 'del']

    def run(self):
        '''
        Deletes an existing local database and its filestore.
        '''

        if not self.db_exists_all():
            raise InvalidDatabase(f'Database {self.database} does not exist')

        if self.db_runs():
            raise RunningOdooDatabase(f'Database {self.database} is running, please shut it down and retry')

        _logger.warning(
            f'You are about to delete the database {self.database} and its filestore. '
            'This action is irreversible.'
        )

        if not _logger.confirm(f'Delete database `{self.database}` and its filestore?'):
            raise CommandAborted()

        filestore = self.db_filestore()
        _logger.info(f'Deleting PSQL database {self.database}')
        query = f'''DROP DATABASE "{self.database}";'''
        result = self.run_queries(query, database=DEFAULT_DATABASE)

        if not result or self.db_exists_all():
            return 1

        _logger.info('Deleted database')

        if not os.path.exists(filestore):
            _logger.info('Filestore not found, no action taken')
        else:
            try:
                _logger.info(f'Attempting to delete filestore in `{filestore}`')
                shutil.rmtree(filestore)
            except Exception as exc:
                _logger.warning(f'Error while deleting filestore: {exc}')
            else:
                _logger.info('Deleted filestore from disk')

        if self.database in self.config['databases']:
            self.config['databases'].delete(self.database)

        return 0
