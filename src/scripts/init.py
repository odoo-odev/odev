# -*- coding: utf-8 -*-

import os
import re
import subprocess
from git import Repo
from clint.textui import colored

from . import script
from .. import utils

re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')

class InitScript(script.Script):
    
    def run(self, database, options):
        """
        Initializes a local Odoo database with the base module then exit the process.
        """

        if not self.db_exists_all(database):
            raise Exception('Database %s does not exist' % (database))

        if self.db_exists(database):
            return 0

        utils.require('version', options[0])

        try:
            match = re_version.match(options[0])
            version = match.group(0)
        except:
            raise Exception('Invalid version number \'%s\'' % (options[0]))

        odoodir = '%s/%s' % (self.config['paths']['odoo'], version)
        odoobin = '%s/odoo/odoo-bin' % (odoodir)
        
        if not os.path.isfile(odoobin):
            utils.log('warning', 'Missing files for Odoo version %s' % (version))
            
            if not utils.confirm('Do you want to download them now?'):
                utils.log('info', 'Action canceled')
                return 0

            utils.mkdir(odoodir, 0o777)

            def clone(title, name):
                 utils.log('info', 'Downloading Odoo %s version %s' % (title, version))
                 Repo.clone_from('git@github.com:odoo/%s.git' % (name), '%s/%s' % (odoodir, name), multi_options=['--branch %s' % (version), '--single-branch'])

            clone('Community', 'odoo')
            clone('Enterprise', 'enterprise')
            clone('Design Themes', 'design-themes')
        
        def pull(title, name):
            utils.log('info', 'Checking for updates in Odoo %s version %s' % (title, version))
            repo = Repo('%s/%s' % (odoodir, name))
            head = repo.head.ref
            tracking = head.tracking_branch()
            pending = len(list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}')))
        
            if pending > 0:
                utils.log('warning', 'You are %s commits behind %s, consider pulling the lastest changes' % (colored.red(pending), tracking))
                
                if utils.confirm('Do you want to pull those commits now?'):
                    utils.log('info', 'Pulling %s commits' % (pending))
                    repo.remotes.origin.pull()
                    utils.log('success', 'Up to date!')

            else:
                utils.log('success', 'Up to date!')

        pull('Community', 'odoo')
        pull('Enterprise', 'enterprise')
        pull('Design Themes', 'design-themes')
        
        addons =  [
            odoodir + '/enterprise',
            odoodir + '/design-themes',
            odoodir + '/odoo/odoo/addons',
            odoodir + '/odoo/addons',
        ]

        command = '%s -d %s --addons-path=%s -i base --stop-after-init' % (odoobin, database, ','.join(addons))
        utils.log('info', 'Running: %s' % (command))
        subprocess.run(command, shell=True, check=True)

        return 0
