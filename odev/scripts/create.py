"""Creates a new empty PostgreSQL database (not Odoo-initialized)."""

import logging
from argparse import ArgumentParser, Namespace

from .database import LocalDBCommand
from .. import utils


_logger = logging.getLogger(__name__)


class CreateScript(LocalDBCommand):
    command = "create"
    help = """
        Creates a new, empty, local PostgreSQL database, not initialized with Odoo.
        Optionally using a template to copy the new database from.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "template",
            nargs='?',
            help="Optional: name of an existing PostgreSQL database to copy",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        if args.template:
            utils.dbname_validate(args.template)
        self.template = args.template

    def run(self):
        """
        Creates a new, empty database locally.
        """

        if self.db_exists_all():
            message = 'but is not an Odoo database'

            if self.db_exists():
                message = 'and is an Odoo database'

            raise Exception(f'Database {self.database} already exists {message}')

        if self.template and self.db_exists_all(database=self.template):
            self.ensure_stopped(database=self.template)

        _logger.info(f'Creating database {self.database}')
        result = self.db_create(template=self.template)

        if not result or not self.db_exists_all(self.database):
            return 1

        _logger.info(f'Created database {self.database}')

        self.clear_db_cache()

        return 0
