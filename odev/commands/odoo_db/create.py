'''Creates a new empty PostgreSQL database (not Odoo-initialized).'''

from argparse import Namespace

from odev.structures import commands
from odev.utils import logging
from odev.exceptions import InvalidDatabase
from odev.constants import DEFAULT_DATABASE


_logger = logging.getLogger(__name__)


class CreateCommand(commands.LocalDatabaseCommand):
    '''
    Create a new empty local PostgreSQL database without initializing it with Odoo.
    Effectively a wrapper around `pg_create` with extra checks.
    '''

    name = 'create'
    aliases = ['cr']
    arguments = [
        dict(
            aliases=['template'],
            nargs='?',
            help='Name of an existing PostgreSQL database to copy',
        )
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.template = args.template or None

    def run(self):
        '''
        Creates a new, empty database locally.
        '''

        if self.db_exists_all():
            message = 'but is not an Odoo database'

            if self.db_exists():
                message = 'and is an Odoo database'

            raise InvalidDatabase(f'Database {self.database} already exists {message}')

        _logger.info(f'Creating database {self.database}')
        query = f'''CREATE DATABASE "{self.database}";'''

        if self.template and self.db_exists_all(database=self.template):
            self.ensure_stopped(database=self.template)
            query = f'''CREATE DATABASE "{self.database}" WITH TEMPLATE "{self.template}";'''

        result = self.run_queries(query, database=DEFAULT_DATABASE)

        if not result or not self.db_exists_all(self.database):
            raise InvalidDatabase(f'Database {self.database} could not be created')

        _logger.info(f'Created database {self.database}')
        return 0
