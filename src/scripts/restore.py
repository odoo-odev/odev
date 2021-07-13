"""Restores an Odoo dump file to a local database with its filestore."""

import logging
import os
import re
import shutil
import subprocess
from argparse import ArgumentParser, Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .database import LocalDBCommand
from .. import utils


_logger = logging.getLogger(__name__)


re_ext = re.compile(r'\.([a-z]+)$')


class RestoreScript(LocalDBCommand):
    command = "restore"
    help = """
        Restores an Odoo dump file to a local database and imports its filestore
        if present. '.sql', '.dump' and '.zip' files are supported.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "dump",
            metavar="PATH",
            help="Path to the dump file to import to the database",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path = args.dump

    def run(self):
        """
        Restores a dump file to a local database.
        """

        if not self.db_exists_all():
            raise Exception(f'Database {self.database} does not exist')

        if self.db_exists() and self.db_runs():
            raise Exception(f'Database {self.database} is running, please shut it down and retry')

        if self.db_exists():
            _logger.warning(f'Database {self.database} is already an Odoo database')

            if not utils.confirm('Do you want to overwrite its content?'):
                _logger.info('Action canceled')
                return 0

        if not os.path.isfile(self.dump_path):
            raise Exception(f'File {self.dump_path} does not exists')

        match = re_ext.search(self.dump_path)

        if not match:
            raise Exception(f'File "{self.dump_path}" has no extension, couldn\'t guess what to do...')

        ext = match.group(1)

        if ext not in ('dump', 'zip', 'sql'):
            raise Exception(f'Unrecognized extension "{ext}" for file {self.dump_path}')

        _logger.info(f'Restoring dump file "{self.dump_path}" to database {self.database}')
        _logger.warning('This may take a while, please be patient...')

        def pg_subprocess(commandline):
            nonlocal self
            _logger.info(f'Importing SQL data to database {self.database}')
            subprocess.run(commandline, shell=True, check=True, stdout=subprocess.DEVNULL)

        def pg_restore(database, dump_path):
            pg_subprocess(["pg_restore", *("-d", database), dump_path])

        def psql_load(database, sql_file):
            pg_subprocess(f'psql "{database}" < "{sql_file}"')

        if ext == "dump":
            pg_restore(self.database, self.dump_path)
        elif ext == "sql":
            psql_load(self.database, self.dump_path)
        elif ext == 'zip':
            with TemporaryDirectory() as tempdir, ZipFile(self.dump_path, 'r') as zipref:
                zipref.extractall(tempdir)

                tmp_sql_path = os.path.join(tempdir, "dump.sql")
                if not os.path.isfile(tmp_sql_path):
                    raise Exception(f'Could not extract "dump.sql" from {self.dump_path}')

                tmp_filestore_path = os.path.join(tempdir, "filestore")
                if os.path.isdir(tmp_filestore_path):
                    filestores_root = Path.home() / '.local/share/Odoo/filestore'
                    filestore_path = str(filestores_root / self.database)
                    _logger.info(f'Filestore detected, installing to {filestore_path}')

                    if os.path.isdir(filestore_path):
                        # TODO: Maybe ask for confirmation
                        _logger.warning(f'Deleting existing filestore directory')
                        shutil.rmtree(filestore_path)

                    shutil.copytree(tmp_filestore_path, filestore_path)

                psql_load(self.database, tmp_sql_path)

        self.clear_db_cache()

        self.dbconfig.add_section(self.database)
        self.db_config(
            version_clean=self.db_version_clean(self.database),
            version=self.db_version(self.database),
            enterprise='enterprise' if self.db_enterprise(self.database) else 'standard',
        )

        with open(Path.home() / '.config/odev/databases.cfg', 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
