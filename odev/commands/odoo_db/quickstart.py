'''Quickly and easily setups a database from a version no., dump or url.'''

import os
import re
import shutil
from argparse import Namespace
from datetime import datetime

from odev.structures import commands
from odev.commands.odoo_db import create, dump, init, remove, restore
from odev.utils import logging


_logger = logging.getLogger(__name__)


re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
re_url = re.compile(
    r'^https?:\/\/|(?:[a-zA-Z0-9-_]+(?:\.dev)?\.odoo\.(com|sh)|localhost|127\.0\.0\.[0-9]+)'
)

TMP_DIR = '/tmp/odev'


class QuickStartCommand(commands.LocalDatabaseCommand):
    '''
    Quickly setup a local database and start working with it directly.

    This command performs the following actions:
      - Create a new, empty database
      - Initialize, dump and restore or restore an existing dump
      - Clean the database so that it can be used for development
    '''

    name = 'quickstart'
    aliases = ['qs']

    arguments = [
        dict(
            aliases=['source'],
            metavar='VERSION|PATH|URL',
            help='''
            One of the following:
              - an Odoo version number to create and init an empty database
              - a path to a local dump file to restore to a new database
              - a url to an Odoo SaaS or SH database to dump and restore locally
            ''',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.subarg = args.source

    def run(self):
        '''
        Creates, initializes or restores and cleanses a local database.
        '''
        if re_version.match(self.subarg):
            mode = 'version'
        elif re_url.match(self.subarg):
            mode = 'url'
        else:
            mode = 'file'

        result = create.CreateCommand.run_with(**self.args.__dict__, template=None)
        if result != 0:
            return result

        try:
            if mode == 'version':
                result = init.InitCommand.run_with(**self.args.__dict__, version=self.subarg)
            else:
                if mode == 'url':
                    result = dump.DumpCommand.run_with(
                        **self.args.__dict__,
                        url=self.subarg,
                        destination=TMP_DIR,
                    )
                    if result != 0:
                        return result

                    timestamp = datetime.now().strftime('%Y%m%d')
                    basename = f'{timestamp}_{self.database}.dump'

                    possible_ext = ('zip', 'dump', 'sql')
                    for ext in possible_ext:
                        filename = os.path.extsep.join((basename, ext))
                        filepath = os.path.join(TMP_DIR, filename)
                        if os.path.isfile(filepath):
                            break
                    else:
                        raise Exception(
                            f'An error occured while fetching dump file at {basename}.<ext> '
                            f'(tried {possible_ext} extensions)'
                        )

                else:  # mode == 'file'
                    filepath = self.subarg

                result = restore.RestoreCommand.run_with(**self.args.__dict__, dump=filepath)

                if result != 0:
                    return result

        except Exception as exception:
            _logger.error('An error occured, cleaning up files and removing database:')
            _logger.error(str(exception))
            remove.RemoveCommand.run_with(**self.args.__dict__)
            result = 1

        finally:
            if os.path.isdir(TMP_DIR):
                shutil.rmtree(TMP_DIR)

        return result