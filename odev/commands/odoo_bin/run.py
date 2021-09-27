'''Runs a local Odoo database.'''

import os
import shlex
import subprocess
from argparse import Namespace, REMAINDER
from datetime import datetime

from odev.structures import commands, actions
from odev.utils import logging, odoo
from odev.exceptions.odoo import RunningOdooDatabase
from odev.constants import ODOO_ADDON_PATHS


logger = logging.getLogger(__name__)


class RunCommand(commands.LocalDatabaseCommand):
    '''
    Run a local Odoo database, prefilling common addon paths and making
    sure the right version of Odoo is installed and in use.

    If the version of Odoo required for the database is not present, download and install it locally.
    This is done by cloning the Odoo community, enterprise and design-themes repositories
    multiple times (once per version) to always keep a copy of each version on the computer.
    To save storage space, only one branch is cloned per version, keeping all other branches out of
    the history.
    '''

    name = 'run'
    arguments = [
        dict(
            aliases=['addons'],
            action=actions.CommaSplitAction,
            nargs='?',
            help='Comma-separated list of additional addon paths',
        ),
        dict(
            aliases=['args'],
            nargs=REMAINDER,
            help='''
            Additional arguments to pass to odoo-bin; Check the documentation at
            https://www.odoo.com/documentation/14.0/fr/developer/misc/other/cmdline.html
            for the list of available arguments
            ''',
        ),
    ]

    odoobin_subcommand = None
    '''
    Optional subcommand to pass to `odoo-bin` at execution time.
    '''

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.addons = args.addons or []
        self.additional_args = args.args

    def run(self):
        '''
        Runs a local Odoo database.
        '''

        self.check_database()

        if self.db_runs():
            raise RunningOdooDatabase(f'Database {self.database} is already running')

        if not self.addons:
            logger.warning(
                'No additional addons specified. '
                'Will try adding the current directory, otherwise will run as enterprise',
            )

        version = self.db_version_clean()

        odoodir = os.path.join(self.config['odev'].get('paths', 'odoo'), version)
        odoobin = os.path.join(odoodir, 'odoo/odoo-bin')

        odoo.pre_run(odoodir, odoobin, version)

        addons = [odoodir + addon_path for addon_path in ODOO_ADDON_PATHS]
        addons += [os.getcwd(), *self.addons]
        addons = [path for path in addons if odoo.is_addon_path(path)]

        python_exec = os.path.join(odoodir, 'venv/bin/python')
        addons_path = ','.join(addons)
        command_args = [
            python_exec,
            odoobin,
            *('-d', self.database),
            f'--addons-path={addons_path}',
            *self.additional_args,
        ]

        if self.odoobin_subcommand:
            command_args.insert(2, self.odoobin_subcommand)

        self.config['databases'].set(
            self.database,
            'lastrun',
            datetime.now().strftime('%a %d %B %Y, %H:%M:%S'),
        )

        command = shlex.join(command_args)
        logger.info(f'Running:\n{command}\n')
        subprocess.run(command, shell=True, check=True)

        return 0