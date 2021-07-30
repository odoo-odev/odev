"""Removes a local database from PostgreSQL and deletes its filestore."""

import os
import shutil
from pathlib import Path

from .database import LocalDBCommand
from .. import utils


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

        utils.log('warning', f'You are about to delete the database {self.database} and its filestore. This action is irreversible.')

        if not utils.confirm(f'Delete database "{self.database}" and its filestore?'):
            utils.log('info', 'Action canceled')
            return 0

        filestore = self.db_filestore()
        utils.log('info', f'Deleting PSQL database {self.database}')
        result = self.db_drop()

        if not result or self.db_exists_all():
            return 1

        utils.log('info', 'Deleted database')

        if not os.path.exists(filestore):
            utils.log('info', 'Filestore not found, no action taken')
        else:
            try:
                utils.log('info', f'Attempting to delete filestore in "{filestore}"')
                shutil.rmtree(filestore)
            except Exception as exc:
                utils.log('warning', f'Error while deleting filestore: {exc}')
            else:
                utils.log('info', 'Deleted filestore from disk')

        self.dbconfig.remove_section(self.database)

        with open(Path.home() / '.config/odev/databases.cfg', 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
