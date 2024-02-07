"""Rename a local database and move its filestore."""

import shutil
from typing import cast

from odev.common import args, progress
from odev.common.commands import LocalDatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess


logger = logging.getLogger(__name__)


class RenameCommand(LocalDatabaseCommand):
    """Rename a local database and move its filestore to the correct path."""

    name = "rename"
    aliases = ["mv", "move"]

    new_name = args.String(
        name="name",
        help="New name for the database.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.odoobin = cast(OdoobinProcess, self.database.process)

        if self.odoobin.is_running:
            if not self.args.force:
                raise self.error(f"Database {self.database.name!r} is running, stop it and retry")

            self.odoobin.kill()

        new_database = LocalDatabase(self.args.name)

        if new_database.exists:
            raise self.error(f"Database with name {self.args.name!r} already exists")

        self.old_filestore = self.database.filestore.path
        self.new_filestore = new_database.filestore.path

    def run(self):
        with progress.spinner(f"Renaming database {self.database.name!r} to {self.args.name!r}"):
            self.rename_database()

        self.move_filestore()
        self.move_configuration()
        logger.info(f"Renamed database {self.database.name!r} to {self.args.name!r}.")

    def rename_database(self):
        """Rename the database in PostgreSQL."""
        self.database.connector.disconnect()

        with self.database.psql() as psql:
            psql.query(
                f"""
                ALTER DATABASE "{self.database.name}"
                RENAME TO "{self.args.name}"
                """
            )

    def move_filestore(self):
        """Move the filestore to the new path."""
        if not self.old_filestore.exists():
            return

        if self.new_filestore.exists():
            if not self.console.confirm(f"Filestore {self.new_filestore} already exists, overwrite?"):
                raise self.error("Command aborted")

            shutil.rmtree(self.new_filestore)

        self.old_filestore.rename(self.new_filestore)

    def move_configuration(self):
        """Rename the database in the stored configuration."""
        with self.database.psql(self.odev.name) as psql:
            psql.query(
                f"""
                UPDATE databases
                    SET name = '{self.args.name}'
                    WHERE name = '{self.database.name}'
                """
            )
