'''Upgrades a local Odoo database.'''

import os
import shlex
import subprocess
from subprocess import DEVNULL
from argparse import Namespace
from datetime import datetime

from odev.utils import logging, odoo
from odev.utils.signal import capture_signals
from odev.exceptions.odoo import RunningOdooDatabase
from odev.constants import ODOO_ADDON_PATHS
from odev.commands.odoo_bin import run


logger = logging.getLogger(__name__)


class UpgradeCommand(run.RunCommand):
    '''
    Upgrade a local Odoo database, running migration scripts between each major versions.
    '''

    name = 'upgrade'
    arguments = [
        dict(
            aliases=['target'],
            help='Odoo version to target; must match an Odoo community branch',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.target = args.target

    def run(self):
        '''
        Upgrade a local Odoo database.
        '''

        self.check_database()

        if self.db_runs():
            raise RunningOdooDatabase(f'Database {self.database} is already running, please shut it down first')

        pre_upgrade_version = self.db_version_clean()

        if self.target == pre_upgrade_version:
            logger.success(f'Database {self.database} is already running version {self.target}, nothing to migrate')
            return 0
        elif self.target <= pre_upgrade_version:
            logger.error(f'Database {self.database} is running a newer version than {self.target}, cannot downgrade')
            return 1

        if not self.addons:
            logger.warning(
                'No additional addons specified. '
                'Will try adding the current directory, otherwise will run as enterprise',
            )

        for version in range(int(float(pre_upgrade_version)), int(float(self.target))):
            current_version = '{:1.1f}'.format(version)
            target_version = '{:1.1f}'.format(version + 1)

            print()  # Empty newline for visual distinction between single upgrades
            logger.info(f'Starting migration of {self.database} [{current_version} -> {target_version}]')

            odoodir = os.path.join(self.config['odev'].get('paths', 'odoo'), target_version)
            odoobin = os.path.join(odoodir, 'odoo/odoo-bin')

            odoo.pre_run(odoodir, odoobin, target_version, upgrade=True)

            addons = [odoodir + addon_path for addon_path in ODOO_ADDON_PATHS]
            addons += [os.getcwd(), *self.addons]
            addons = [path for path in addons if odoo.is_addon_path(path)]

            odoo.prepare_requirements(odoodir, addons=addons)

            python_exec = os.path.join(odoodir, 'venv/bin/python')
            addons_path = ','.join(addons)
            command_args = [
                python_exec,
                odoobin,
                *('-d', self.database),
                f'--addons-path={addons_path}',
                *('-u', 'all'),
                '--stop-after-init',
                *self.additional_args,
            ]

            upgrade_path = os.path.normpath(os.path.join(odoodir, '..', 'upgrade', 'migrations'))

            if version >= 12:
                # Target version is higher or equal than 13.0 so we have to account
                # for the new `--upgrade-path` parameter
                command_args.insert(5, f'''--upgrade-path={upgrade_path}''')
            else:
                # The `--upgrade-path` parameter didn't exist prior to Odoo version 13.0,
                # we have to include it as an addon by creating a symbolic link between
                # the upgrade repository and the targeted Odoo version addons
                odoo_path = os.path.join(odoodir, 'odoo', 'odoo', 'addons', 'base', 'maintenance')
                rm_command = shlex.join(['rm', '-f', odoo_path])
                ln_command = shlex.join(['ln', '-s', upgrade_path, odoo_path])

                subprocess.run(rm_command, shell=True, check=True, stderr=DEVNULL)
                subprocess.run(ln_command, shell=True, check=True, stderr=DEVNULL)

            self.config['databases'].set(
                self.database,
                'lastrun',
                datetime.now().strftime('%a %d %B %Y, %H:%M:%S'),
            )

            command = shlex.join(command_args)
            logger.info(f'Running: {command}')

            with capture_signals():
                subprocess.run(command, shell=True, check=True)

                self.config['databases'].set(self.database, 'version_clean', self.db_version_clean())
                self.config['databases'].set(self.database, 'version', self.db_version())

                logger.info(f'Migrated {self.database} [{current_version} -> {target_version}]')

        logger.success(f'Successfully migrated {self.database} [{pre_upgrade_version} -> {self.target}]')
        return 0
