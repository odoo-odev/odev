"""Removes a local database from PostgreSQL and deletes its filestore."""

from argparse import Namespace

from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class RemoveCommand(commands.LocalDatabaseCommand):
    """
    Drop a local database in PostgreSQL and delete its Odoo filestore on disk.
    """

    name = "remove"
    aliases = ["rm", "del"]
    arguments = [
        {
            "aliases": ["--keep-filestore"],
            "action": "store_true",
            "help": "Do not delete the filestore for the db",
        },
        {
            "aliases": ["--keep-template"],
            "action": "store_true",
            "help": "Preserve the associated template db. Implies --keep-filestore",
        },
        {
            "aliases": ["--keep-venv"],
            "action": "store_true",
            "help": "Do not delete the db-specific venv, if any",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.keep_template: bool = args.keep_template
        self.keep_filestore: bool = self.keep_template or args.keep_filestore
        self.keep_venv = args.keep_venv

    def run(self):
        """
        Deletes an existing local database and its filestore.
        """
        return super().remove(
            keep_template=self.keep_template, keep_filestore=self.keep_filestore, keep_venv=self.keep_venv
        )
