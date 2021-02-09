# -*- coding: utf-8 -*-

import os
import subprocess
from clint.textui import colored

from . import script
from .. import utils


class RunScript(script.Script):

    def run(self, database, options):
        """
        Runs a local Odoo database.
        """

        self.db_is_valid(database)

        if self.db_runs(database):
            raise Exception('Database %s is already running' % (database))

        version = self.db_version_clean(database)

        odoodir = '%s/%s' % (self.config['paths']['odoo'], version)
        odoobin = '%s/odoo/odoo-bin' % (odoodir)

        utils.pre_run(odoodir, odoobin, version)

        addons =  [
            odoodir + '/enterprise',
            odoodir + '/design-themes',
            odoodir + '/odoo/odoo/addons',
            odoodir + '/odoo/addons',
        ]

        if options[0] and not str(options[0][0]) == '-':
            addons += options.pop(0).split(',')

        command = '%s/venv/bin/python %s -d %s --addons-path=%s %s' % (odoodir, odoobin, database, ','.join(addons), ' '.join(options.all))
        utils.log('info', 'Running: \n%s\n' % (command))
        subprocess.run(command, shell=True, check=True)

        return 0
