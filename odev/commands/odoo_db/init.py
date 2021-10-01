'''Initializes an empty PostgreSQL database for a specific Odoo version.'''

import os
import re
import shlex
import subprocess
from argparse import Namespace

from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')


class InitCommand(commands.LocalDatabaseCommand):
    '''
    Initialize an empty PSQL database with the base version of Odoo for a given major version.
    '''

    name = 'init'
    arguments = [
        dict(
            aliases=['version'],
            help='Odoo version to use; must match an Odoo community branch',
        )
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.version = args.version

    def run(self):
        '''
        Initializes a local Odoo database with the base module then exit
        the process.
        '''

        if not self.db_exists_all():
            raise Exception(f'Database {self.database} does not exist')

        if self.db_exists():
            _logger.info(f'Database {self.database} is already initialized')
            return 0

        match = re_version.match(self.version)

        if not match:
            raise Exception(f'Invalid version number `{self.version}`')

        version = match and match.group(0)

        odoodir = os.path.join(self.config['odev'].get('paths', 'odoo'), version)
        odoobin = os.path.join(odoodir, 'odoo/odoo-bin')

        odoo.pre_run(odoodir, odoobin, version)

        addons = [
            odoodir + '/enterprise',
            odoodir + '/design-themes',
            odoodir + '/odoo/odoo/addons',
            odoodir + '/odoo/addons',
        ]

        python_exec = os.path.join(odoodir, 'venv/bin/python')
        addons_path = ','.join(addons)
        command = shlex.join(
            [
                python_exec,
                odoobin,
                *('-d', self.database),
                f'--addons-path={addons_path}',
                *('-i', 'base'),
                '--stop-after-init',
                '--without-demo=all',
            ]
        )
        _logger.info(f'Running: {command}')

        with capture_signals():
            subprocess.run(command, shell=True, check=True)

        self.config['databases'].set(self.database, 'version_clean', version)

        return 0
