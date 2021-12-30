'''Runs a local Odoo database.'''

import os
import shlex
import subprocess
from argparse import Namespace, REMAINDER
from datetime import datetime

from odev.structures import commands, actions
from odev.utils import logging, odoo
from odev.utils.signal import capture_signals
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
            aliases=['-s', '--save'],
            dest='save',
            action='store_true',
            help='Save the current arguments for next calls',
        ),
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

    force_save_args = False
    '''
    Whether to force re-saving arguments to the database's config
    within subcommands.
    '''

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.config_args_key = f'args_{self.name}'
        config_args = list(filter(
            lambda s: s,
            self.config['databases'].get(self.database, self.config_args_key, '').split(' ')
        ))

        self.addons = args.addons or (
            [config_args.pop(0)] if config_args[:1] and os.path.isdir(config_args[0]) else []
        )
        self.additional_args = args.args or config_args

        if args.save and (
            not config_args
            or logger.confirm('Arguments have already been saved for this database, do you want to override them?')
        ):
            self.force_save_args = True
            self.config['databases'].set(
                self.database,
                self.config_args_key,
                shlex.join([*self.addons, *self.additional_args]),
            )

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

        repos_path = self.config['odev'].get('paths', 'odoo')
        version_path = odoo.repos_version_path(repos_path, version)
        odoobin = os.path.join(version_path, 'odoo/odoo-bin')

        odoo.prepare_odoobin(repos_path, version)

        addons = [version_path + addon_path for addon_path in ODOO_ADDON_PATHS]
        addons += [os.getcwd(), *self.addons]
        addons = [path for path in addons if odoo.is_addon_path(path)]
        odoo.prepare_requirements(repos_path, version, addons=addons)

        python_exec = os.path.join(version_path, 'venv/bin/python')
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
        logger.debug(f'Running: {command}')

        with capture_signals():
            subprocess.run(command, shell=True, check=True)

        return 0
