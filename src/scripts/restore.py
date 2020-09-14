# -*- coding: utf-8 -*-

import os
import re
import tempfile
import zipfile
import shutil
import subprocess
from pathlib import Path

from . import script
from .. import utils

re_ext = re.compile(r'\.([a-z]+)$')

class RestoreScript(script.Script):
    
    def run(self, database, options):
        """
        Restores a dump file to a local database.
        """

        if not self.db_exists_all(database):
            raise Exception('Database %s does not exist' % (database))

        if self.db_exists(database) and self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

        if self.db_exists(database):
            utils.log('warning', 'Database %s is already an Odoo database' % (database))

            if not utils.confirm('Do you want to overwrite its content?'):
                utils.log('info', 'Action canceled')
                return 0

        dumpfile = options[0]

        if not dumpfile:
            raise Exception('No dump file specified')

        if not os.path.isfile(dumpfile):
            raise Exception('File %s does not exists' % (dumpfile))

        match = re_ext.search(dumpfile)
        
        if not match:
            raise Exception('File \'%s\' has no extension, couldn\'t guess what to do...' % (dumpfile))

        ext = match.group(1)

        if not ext in ['dump', 'zip', 'sql']:
            raise Exception('Unrecognized extension \'.%s\' for file %s' % (ext, dumpfile))
        
        utils.log('info', 'Restoring dump file \'%s\' to database %s' % (dumpfile, database))
        utils.log('warning', 'This may take a while, please be patient...')
        
        if ext == 'dump':
            subprocess.run('pgrestore -d %s %s' % (database, dumpfile), shell=True, check=True, stdout=subprocess.DEVNULL)
        if ext == 'sql':
            subprocess.run('psql %s < %s' % (database, dumpfile), shell=True, check=True, stdout=subprocess.DEVNULL)
        if ext == 'zip':
            tempdir = tempfile.TemporaryDirectory()

            with zipfile.ZipFile(dumpfile, 'r') as zipref:
                zipref.extractall(tempdir.name)

                if not os.path.isfile('%s/dump.sql' % (tempdir.name)):
                    raise Exception('Could not extract \'dump.sql\' from %s' % (dumpfile))

                if os.path.isdir('%s/filestore' % (tempdir.name)):
                    filestoredir = '%s/.local/share/Odoo/filestore' % (os.path.expanduser('~'))
                    utils.log('info', 'Filestore detected, installing to %s/%s/' % (filestoredir, database))
                    
                    if os.path.isdir('%s/%s' % (filestoredir, database)):
                        shutil.rmtree('%s/%s' % (filestoredir, database))

                    shutil.copytree('%s/filestore' % (tempdir.name), '%s/%s' % (filestoredir, database))

                utils.log('info', 'Importing SQL data to database %s' % (database))
                subprocess.run('psql %s < %s/dump.sql' % (database, tempdir.name), shell=True, check=True, stdout=subprocess.DEVNULL)

        self.dbconfig.add_section(database)
        self.db_config(database, [
            ('version_clean', self.db_version_clean(database)),
            ('version', self.db_version(database)),
            ('enterprise', 'enterprise' if self.db_enterprise(database) else 'standard'),
        ])

        with open('/etc/odev/databases.cfg', 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
