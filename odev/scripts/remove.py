"""Removes a local database from PostgreSQL and deletes its filestore."""

import logging
import os
import shutil
from pathlib import Path

from .database import LocalDBCommand
from .. import utils


_logger = logging.getLogger(__name__)


class RemoveScript(LocalDBCommand):
    command = "remove"
    aliases = ("rm",)
    help = "Removes a local database from PostgreSQL and deletes its filestore."

    def run(self):
        """
        Deletes an existing local database and its filestore.
        """

        if not self.db_exists_all():
            raise Exception(f'Database {self.database} does not exist')

        if self.db_runs():
            raise Exception(f'Database {self.database} is running, please shut it down and retry')

        _logger.warning(f'You are about to delete the database {self.database} and its filestore. This action is irreversible.')

        if not utils.confirm(f'Delete database "{self.database}" and its filestore?'):
            _logger.info('Action canceled')
            return 0

        filestore = self.db_filestore()
        _logger.info(f'Deleting PSQL database {self.database}')
        result = self.db_drop()

        if not result or self.db_exists_all():
            return 1

        _logger.info('Deleted database')

        if not os.path.exists(filestore):
            _logger.info('Filestore not found, no action taken')
        else:
            try:
                _logger.info(f'Attempting to delete filestore in "{filestore}"')
                shutil.rmtree(filestore)
            except Exception as exc:
                _logger.warning(f'Error while deleting filestore: {exc}')
            else:
                _logger.info('Deleted filestore from disk')

        self.clear_db_cache()

        self.dbconfig.remove_section(self.database)

        with open(Path.home() / '.config/odev/databases.cfg', 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
