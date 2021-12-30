'''Initializes an empty PostgreSQL database for a specific Odoo version.'''

import os
import re
import shlex
import subprocess
from argparse import Namespace

from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.signal import capture_signals
from odev.exceptions import InvalidQuery
from odev.constants.odoo import ODOO_ADDON_PATHS


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
    queries = [
        'CREATE SCHEMA unaccent_schema',
        'CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA unaccent_schema',
        'COMMENT ON EXTENSION unaccent IS \'text search dictionary that removes accents\'',
        '''
        CREATE FUNCTION public.unaccent(text) RETURNS text
            LANGUAGE sql IMMUTABLE
            AS $_$
                SELECT unaccent_schema.unaccent('unaccent_schema.unaccent', $1)
            $_$
        ''',
        'GRANT USAGE ON SCHEMA unaccent_schema TO PUBLIC',
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

        repos_path = self.config['odev'].get('paths', 'odoo')
        version_path = os.path.join(repos_path, version)  # TODO: DRY, make global fn
        odoobin = os.path.join(version_path, 'odoo/odoo-bin')

        odoo.prepare_odoobin(repos_path, version)

        addons = [version_path + addon_path for addon_path in ODOO_ADDON_PATHS]
        odoo.prepare_requirements(version_path, addons=addons)

        python_exec = os.path.join(version_path, 'venv/bin/python')
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

        result = self.run_queries(self.queries)

        if not result:
            raise InvalidQuery(f'An error occurred while setting up database {self.database}')

        self.config['databases'].set(self.database, 'version_clean', version)

        return 0
