# -*- coding: utf-8 -*-

import os
import subprocess
from clint.textui import colored

from . import script
from .. import utils


class RunScript(script.Script):

    usage = "run <database> <addons> [<options>]"
    args = [
        ['database', 'Name of the local database to run'],
        ['addons  ', 'List of addon paths to add to the default ones, separated by a coma (,)'],
        ['options ', 'Optional: additional arguments to pass to odoo-bin']
    ]
    description = """
Runs a local Odoo database, prefilling common addon paths and making
sure the right version of Odoo is installed and in use.

If the version of Odoo required for the database is not present, downloads it
and installs it locally. This is done by cloning the Odoo community,
enterprise and design-themes repositories multiple times (one per version)
to always keep a copy of each version on the computer. To save storage space,
only one branch is cloned per version, keeping all other branches out of
the history. This means that the sum of the sizes of all independant
local versions should be lower (or roughly equal if all versions are installed)
than the size of the entire Odoo repositories.
"""

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
