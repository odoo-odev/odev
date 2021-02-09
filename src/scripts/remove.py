# -*- coding: utf-8 -*-

import shutil
from pathlib import Path

from . import script
from .. import utils


class RemoveScript(script.Script):

    usage = 'remove <database>'
    alias = ['rm']
    args = [['database', 'Name of the local database to remove']]
    description = """
Removes a local database from PostgreSQL and deletes its filestore.
"""

    def run(self, database, options):
        """
        Deletes an existing local database and its filestore.
        """

        if not self.db_exists_all(database):
            raise Exception('Database %s does not exist' % (database))

        if self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

        utils.log('warning', 'You are about to delete the database %s and its filestore. This action is irreversible.' % (database))

        if not utils.confirm('Delete database \'%s\' and its filestore?' % (database)):
            utils.log('info', 'Action canceled')
            return 0

        filestore = self.db_filestore(database)
        utils.log('info', 'Deleting PSQL database %s' % (database))
        query = 'DROP DATABASE %s;' % (database)
        result = super().run(self.database, query)

        if not result or self.db_exists_all(database):
            return 1

        utils.log('info', 'Deleted database')

        try:
            utils.log('info', 'Attempting to delete filestore in \'%s\'' % (filestore))
            shutil.rmtree(filestore)
        except:
            utils.log('info', 'Filestore not found, no action taken')
        else:
            utils.log('info', 'Deleted filestore from disk')

        self.dbconfig.remove_section(database)

        with open('%s/.config/odev/databases.cfg' % (str(Path.home())), 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
