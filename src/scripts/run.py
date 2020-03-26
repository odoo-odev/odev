# -*- coding: utf-8 -*-

import os
import subprocess
from git import Repo

from . import script
from .. import utils


class RunScript(script.Script):
    
    def run(self, database, options):
        """
        Runs a local Odoo database.
        """

        self.db_valid(database)

        if self.db_runs(database):
            raise Exception('Database %s is already running' % (database))

        version = self.db_version_clean(database)

        odoodir = '%s/%s' % (self.config['paths']['odoo'], version)
        odoobin = '%s/odoo/odoo-bin' % (odoodir)
        
        if not os.path.isfile(odoobin):
            utils.log('warning', 'Missing files for Odoo version %s' % (version))
            
            if not utils.confirm('Do you want to download them now?'):
                utils.log('info', 'Action canceled')
                return 0

            os.makedirs(odoodir, 0o777, exist_ok=True)
            os.chmod(odoodir, 0o777)

            utils.log('info', 'Downloading Odoo Community version %s' % (version))
            Repo.clone_from('git@github.com:odoo/odoo.git', '%s/odoo' % (odoodir), multi_options=['--branch %s' % (version), '--single-branch'])
            
            utils.log('info', 'Downloading Odoo Enterprise version %s' % (version))
            Repo.clone_from('git@github.com:odoo/enterprise.git', '%s/enterprise' % (odoodir), multi_options=['--branch %s' % (version), '--single-branch'])
            
            utils.log('info', 'Downloading Odoo Design Themes version %s' % (version))
            Repo.clone_from('git@github.com:odoo/design-themes.git', '%s/design-themes' % (odoodir), multi_options=['--branch %s' % (version), '--single-branch'])

        addons =  [
            odoodir + '/enterprise',
            odoodir + '/design-themes',
            odoodir + '/odoo/odoo/addons',
            odoodir + '/odoo/addons',
        ]

        if options[0] and not str(options[0][0]) == '-':
            addons += options.pop(0).split(',')

        command = '%s -d %s --addons-path=%s %s' % (odoobin, database, ','.join(addons), ' '.join(options.all))
        utils.log('info', 'Running: %s' % (command))
        subprocess.run(command, shell=True, check=True)

        return 0
