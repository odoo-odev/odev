'''Restores an Odoo dump file to a local database with its filestore.'''

import os
import re
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from odev.structures import commands
from odev.commands.odoo_db import remove, create, clean
from odev.utils import logging
from odev.utils.signal import capture_signals
from odev.exceptions import RunningOdooDatabase, CommandAborted


_logger = logging.getLogger(__name__)


class RestoreCommand(commands.LocalDatabaseCommand):
    '''
    Restore an Odoo dump file to a local database and import its filestore
    if present. '.sql', '.dump' and '.zip' files are supported.
    '''

    name = 'restore'
    arguments = [
        dict(
            aliases=['dump'],
            metavar='PATH',
            help='Path to the dump file to import to the database',
        ),
        dict(
            aliases=['--no-clean'],
            dest='no_clean',
            action='store_true',
            help='Do not attempt to run the `clean` command on the database (useful for upgrades)',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path = args.dump
        self.run_clean = not args.no_clean

    def run(self):
        '''
        Restores a dump file to a local database.
        '''

        if self.db_exists_all():
            if self.db_exists():
                _logger.warning(f'Database {self.database} already exists and is an Odoo database')

                if not _logger.confirm('Do you want to overwrite its content?'):
                    raise CommandAborted()

                remove.RemoveCommand.run_with(**self.args.__dict__)
                create.CreateCommand.run_with(**self.args.__dict__, template=None)
        else:
            _logger.warning(f'Database {self.database} does not exist')

            if not _logger.confirm('Do you want to create it now?'):
                raise CommandAborted()

            create.CreateCommand.run_with(**self.args.__dict__, template=None)

        if self.db_runs():
            raise RunningOdooDatabase(f'Database {self.database} is running, please shut it down and retry')

        if not os.path.isfile(self.dump_path):
            raise FileNotFoundError(f'File {self.dump_path} does not exists')

        _, tail = os.path.split(self.dump_path)
        _, ext = os.path.splitext(tail)

        if not ext:
            raise ValueError(f'File `{self.dump_path}` has no extension, couldn\'t guess what to do...')
        elif ext not in {'.dump', '.zip', '.sql', '.gz'}:
            raise ValueError(f'Unrecognized extension `{ext}` for file {self.dump_path}')

        _logger.info(f'Restoring dump file `{self.dump_path}` to database {self.database}')
        _logger.warning('This may take a while, please be patient...')

        def pg_subprocess(commandline):
            nonlocal self
            _logger.info(f'Importing SQL data to database {self.database}')

            with capture_signals():
                subprocess.run(commandline, shell=True, check=True, stdout=subprocess.DEVNULL)

        def pg_restore(database, dump_path):
            pg_subprocess(['pg_restore', *('-d', database), dump_path])

        def psql_load(database, sql_file):
            pg_subprocess(f'psql "{database}" < "{sql_file}"')

        def psql_pipe(database, cmd):
            pg_subprocess(f'{cmd} | psql "{database}"')

        if ext == '.dump':
            pg_restore(self.database, self.dump_path)
        elif ext == '.sql':
            psql_load(self.database, self.dump_path)
        elif ext == '.gz':
            cmd = f"zcat {self.dump_path}"
            psql_pipe(self.database, cmd)
        elif ext == '.zip':
            with TemporaryDirectory() as tempdir, ZipFile(self.dump_path, 'r') as zipref:
                zipref.extractall(tempdir)

                tmp_sql_path = os.path.join(tempdir, 'dump.sql')
                if not os.path.isfile(tmp_sql_path):
                    raise Exception(f'Could not extract `dump.sql` from {self.dump_path}')

                tmp_filestore_path = os.path.join(tempdir, 'filestore')
                if os.path.isdir(tmp_filestore_path):
                    filestores_root = Path.home() / '.local/share/Odoo/filestore'
                    filestore_path = str(filestores_root / self.database)
                    _logger.info(f'Filestore detected, installing to {filestore_path}')

                    if os.path.isdir(filestore_path):
                        _logger.warning(f'A filestore already exists at `{filestore_path}`')

                        if _logger.confirm('Do you want to overwrite it?'):
                            _logger.warning(f'Deleting existing filestore directory')
                            shutil.rmtree(filestore_path)

                    shutil.copytree(tmp_filestore_path, filestore_path)

                psql_load(self.database, tmp_sql_path)

        db_config = self.config['databases']
        db_config.set(self.database, 'version', self.db_version(self.database))
        db_config.set(self.database, 'version_clean', self.db_version_clean(self.database))
        db_config.set(self.database, 'enterprise', 'enterprise' if self.db_enterprise(self.database) else 'standard')
        db_config.save()

        if self.run_clean:
            clean.CleanCommand.run_with(**self.args.__dict__)

        return 0
