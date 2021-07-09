# -*- coding: utf-8 -*-
from argparse import ArgumentParser, Namespace

from .database import LocalDBCommand, NO_DB
from .. import utils


class CreateScript(LocalDBCommand):
    command = "create"
    help = """
        Creates a new, empty, local PostgreSQL database, not initialized with Odoo.
        Sanitizes the name of the new database so that it can be used within PostgreSQL.
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
        self.template = utils.sanitize(args.template) if args.template else None

    def run(self):
        """
        Creates a new, empty database locally.
        """

        if self.db_exists_all():
            message = 'but is not an Odoo database'

            if self.db_exists():
                message = 'and is an Odoo database'

            raise Exception(f'Database {self.database} already exists {message}')

        utils.log('info', f'Creating database {self.database}')
        query = 'CREATE DATABASE "%s";' % self.database

        if self.template:
            if self.db_exists_all(database=self.template):
                self.ensure_stopped(database=self.template)
                query = 'CREATE DATABASE "%s" WITH TEMPLATE "%s";' % (
                    self.database,
                    self.template,
                )

        result = self.run_queries(query, database=NO_DB)

        if not result or not self.db_exists_all(self.database):
            return 1

        utils.log('info', f'Created database {self.database}')
        return 0
