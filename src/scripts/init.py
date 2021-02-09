# -*- coding: utf-8 -*-

import os
import re
import subprocess
from clint.textui import colored

from . import script
from .. import utils

re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')


class InitScript(script.Script):

    usage = 'init <database> <version>'
    args = [
        ['database', 'Name of the local database to initialize'],
        ['version ', 'Odoo version to use; must correspond to an Odoo community branch']
    ]
    description = """
Initializes an empty PSQL database with a basic version of Odoo.
Basically, installs the base module on an empty DB.
"""

    def run(self, database, options):
        """
        Initializes a local Odoo database with the base module then exit
        the process.
        """

        if not self.db_exists_all(database):
            raise Exception('Database %s does not exist' % (database))

        if self.db_exists(database):
            return 0

        utils.require('version', options[0])

        try:
            match = re_version.match(options[0])
            version = match.group(0)
        except Exception:
            raise Exception('Invalid version number \'%s\'' % (options[0]))

        odoodir = '%s/%s' % (self.config['paths']['odoo'], version)
        odoobin = '%s/odoo/odoo-bin' % (odoodir)

        utils.pre_run(odoodir, odoobin, version)

        addons =  [
            odoodir + '/enterprise',
            odoodir + '/design-themes',
            odoodir + '/odoo/odoo/addons',
            odoodir + '/odoo/addons',
        ]

        command = '%s/venv/bin/python %s -d %s --addons-path=%s -i base --stop-after-init --without-demo=all' % (odoodir, odoobin, database, ','.join(addons))
        utils.log('info', 'Running: \n%s\n' % (command))
        subprocess.run(command, shell=True, check=True)

        return 0
