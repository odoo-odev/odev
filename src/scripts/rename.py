"""Renames a database and its filestore."""

import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from .database import LocalDBCommand, NO_DB
from .. import utils


class RenameScript(LocalDBCommand):
    command = "rename"
    aliases = ("mv",)
    help = "Renames a database and its filestore."

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "new_name",
            help="New name for the database and its filestore",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.new_name = args.new_name

    def run(self):
        """
        Renames a local database and its filestore.
        """
        name_old = self.database
        name_new = self.new_name
        filestores_root = Path.home() / '.local/share/Odoo/filestore'
        filestore_old = str(filestores_root / name_old)
        filestore_new = str(filestores_root / name_new)

        if not self.db_exists_all():
            raise Exception(f'Database {name_old} does not exist')

        if self.db_runs():
            raise Exception(f'Database {name_old} is running, please shut it down and retry')

        if self.db_exists_all(name_new):
            raise Exception(f'Database with name {name_new} already exists')
        # TODO: Maybe check also if filestore with dest name exists (left over)?

        utils.log('warning', f'You are about to rename the database "{name_old}" and its filestore to "{name_new}". This action is irreversible.')

        if not utils.confirm(f'Rename "{name_old} and its filestore?'):
            utils.log('info', 'Action canceled')
            return 0

        utils.log('info', f'Renaming database "{name_old}" to "{name_new}"')
        query = 'ALTER DATABASE "%s" RENAME TO "%s";' % (name_old, name_new)
        result = self.run_queries(query, database=NO_DB)
        utils.log('info', 'Renamed database')

        if not result or self.db_exists_all(name_old) or not self.db_exists_all(name_new):
            return 1

        if not os.path.exists(filestore_old):
            utils.log('info', 'Filestore not found, no action taken')
        try:
            utils.log('info', f'Attempting to rename filestore in "{filestore_old}" to "{filestore_new}"')
            os.rename(filestore_old, filestore_new)
        except Exception as exc:
            utils.log('warning', f'Error while renaming filestore: {exc}')
        else:
            utils.log('info', 'Renamed filestore')

        items = self.dbconfig.items(name_old)
        self.dbconfig.remove_section(name_old)
        self.dbconfig.add_section(name_new)

        for item in items:
            self.dbconfig.set(name_new, item[0], item[1])

        with open(Path.home() / '.config/odev/databases.cfg', 'w') as configfile:
            self.dbconfig.write(configfile)

        return 0
