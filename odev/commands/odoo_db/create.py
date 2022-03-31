"""Creates a new empty PostgreSQL database (not Odoo-initialized)."""
import os
import shutil
from argparse import Namespace

from odev.constants import DEFAULT_DATABASE
from odev.exceptions import CommandAborted, InvalidDatabase
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class CreateCommand(commands.LocalDatabaseCommand):
    """
    Create a new empty local PostgreSQL database without initializing it with Odoo.
    Effectively a wrapper around `pg_create` with extra checks.
    """

    name = "create"
    aliases = ["cr"]
    arguments = [
        {
            "aliases": ["template"],
            "nargs": "?",
            "help": "Name of an existing PostgreSQL database to copy",
        },
        {
            "name": "copy_filestore",
            "dest": "copy_filestore",
            "aliases": ["--no-filestore"],
            "action": "store_false",
            "help": "Do not copy the filestore from the template",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.template = args.template or None
        self.copy_filestore = args.copy_filestore

    def run(self):
        """
        Creates a new, empty database locally.
        """

        if self.db_exists_all():
            message = "but is not an Odoo database"

            if self.db_exists():
                message = "and is an Odoo database"

            raise InvalidDatabase(f"Database {self.database} already exists {message}")

        _logger.info(f"Creating database {self.database}")

        if self.template and self.db_exists_all(database=self.template):
            self.ensure_stopped(database=self.template)

        query = f"""
            CREATE DATABASE "{self.database}"
                WITH TEMPLATE "{self.template or 'template0'}"
                LC_COLLATE 'C'
                ENCODING 'unicode';
        """

        result = self.run_queries(query, database=DEFAULT_DATABASE)

        if not result or not self.db_exists_all(self.database):
            raise InvalidDatabase(f"Database {self.database} could not be created")

        if self.template and self.copy_filestore:
            filestore = self.db_filestore()
            template_filestore = self.db_filestore(self.template)

            if not os.path.exists(template_filestore):
                _logger.info("Template filestore not found, no action taken")
            else:
                if os.path.exists(filestore):
                    if not _logger.confirm(f"The new filestore path already exists: `{filestore}`\nOverwrite it?"):
                        raise CommandAborted
                    _logger.info(f"Deleting previous filestore in `{filestore}`")
                    shutil.rmtree(filestore)

                _logger.info(f"Copying template filestore to `{filestore}`")
                try:
                    shutil.copytree(template_filestore, filestore)
                except Exception as exc:
                    _logger.warning(f"Error while copying filestore: {exc}")

        _logger.info(f"Created database {self.database}")
        return 0
