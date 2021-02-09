# -*- coding: utf-8 -*-

import os
from pathlib import Path

from . import script
from .. import utils


class RenameScript(script.Script):

    usage = 'rename <database> <new_name>'
    alias = ['mv']
    args = [
        ['database', 'Name of the local database to rename'],
        ['new_name', 'New name for the database and its filestore']
    ]
    description = """
Renames a database and its filestore.
"""

    def run(self, database, options):
        """
        Renames a local database and its filestore.
        """

        if not self.db_exists_all(database):
            raise Exception('Database %s does not exist' % (database))

        if self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

        name = utils.sanitize(options[0])

        if self.db_exists_all(name):
            raise Exception('Database %s already exists' % (database))

        utils.log('warning', 'You are about to rename the database %s and its filestore to \'%s\'. This action is irreversible.' % (database, name))

        if not utils.confirm('Rename \'%s\' and its filestore?' % (database)):
            utils.log('info', 'Action canceled')
            return 0

        utils.log('info', 'Renaming database %s to \'%s\'' % (database, name))
        query = 'ALTER DATABASE %s RENAME TO %s;' % (database, name)
        result = super().run(self.database, query)
        utils.log('info', 'Renamed database')

        if not result or self.db_exists_all(database) or not self.db_exists_all(name):
            return 1

        try:
            filestore = '%s/.local/share/Odoo/filestore/' % (str(Path.home()))
            utils.log('info', 'Attempting to rename filestore in \'%s%s\' to \'%s%s\'' % (filestore, database, filestore, name))
            os.rename(filestore + database, filestore + name)
        except Exception:
            utils.log('info', 'Filestore not found, no action taken')
        else:
            utils.log('info', 'Renamed filestore')

        items = self.dbconfig.items(database)
        self.dbconfig.remove_section(database)
        self.dbconfig.add_section(name)

        for item in items:
            self.dbconfig.set(name, item[0], item[1])

        with open('%s/.config/odev/databases.cfg' % (str(Path.home())), 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
