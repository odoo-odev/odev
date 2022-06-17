"""Renames a database and its filestore."""

import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from odev.constants import DEFAULT_DATABASE
from odev.exceptions import CommandAborted
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class RenameCommand(commands.LocalDatabaseCommand):
    """
    Rename a local database and move its filestore to the corresponding path.
    """

    name = "rename"
    aliases = ["mv", "move"]

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
        filestores_root = Path.home() / ".local/share/Odoo/filestore"
        filestore_old = str(filestores_root / name_old)
        filestore_new = str(filestores_root / name_new)

        if not self.db_exists_all():
            raise Exception(f"Database {name_old} does not exist")

        if self.db_runs():
            raise Exception(f"Database {name_old} is running, please shut it down and retry")

        if self.db_exists_all(name_new):
            raise Exception(f"Database with name {name_new} already exists")

        _logger.warning(
            f"You are about to rename the database `{name_old}` and its filestore to `{name_new}`. "
            f"This action is irreversible."
        )

        if not _logger.confirm(f"Rename `{name_old}` and its filestore?"):
            raise CommandAborted()

        _logger.info(f"Renaming database `{name_old}` to `{name_new}`")
        query = f"""ALTER DATABASE "{name_old}" RENAME TO "{name_new}";"""
        result = self.run_queries(query, database=DEFAULT_DATABASE)
        _logger.info("Renamed database")

        if not result or self.db_exists_all(name_old) or not self.db_exists_all(name_new):
            return 1

        if os.path.exists(filestore_new):
            _logger.warning(f"A filestore already exists in `{filestore_new}`")

            if not _logger.confirm("Do you want to overwrite it?"):
                raise CommandAborted()

            os.removedirs(filestore_new)

        if os.path.exists(filestore_old):
            try:
                _logger.info(f"Attempting to rename filestore in `{filestore_old}` to `{filestore_new}`")
                os.rename(filestore_old, filestore_new)
            except Exception as exc:
                _logger.warning(f"Error while renaming filestore: {exc}")
            else:
                _logger.info("Renamed filestore")
        else:
            _logger.info("Filestore not found, no action taken")

        db_config = self.config["databases"]
        db_config[name_new] = db_config[name_old]
        del db_config[name_old]
        db_config.save()

        return 0
