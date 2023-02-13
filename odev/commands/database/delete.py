"""Create a new database."""

import shutil

from odev.common import prompt, style
from odev.common.commands import OdoobinCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class DeleteCommand(OdoobinCommand):
    """Remove a local PostgreSQL database and its associated files."""

    name = "delete"
    aliases = ["remove", "rm"]
    arguments = [
        {
            "name": "keep",
            "aliases": ["-k", "--keep"],
            "action": "store_comma_split",
            "nargs": "?",
            "default": [],
            "help": """List of associated resources to keep, separated by commas. Possible values are:
                - filestore: keep the database filestore
                - template: keep template databases associated to this one
                - venv: keep the virtual environment associated to the database
                - config: keep saved attributes for the database (i.e. whitelist, saved arguments,...)
            """,
        },
    ]

    def run(self):
        """Create a new database locally."""
        if not prompt.confirm(f"Are you sure you want to delete the database {self.database.name!r}?"):
            raise self.error("Command aborted")

        if self.database.whitelisted:
            if not prompt.confirm(f"Database {self.database.name!r} is whitelisted, are you really sure?"):
                raise self.error("Command aborted")

        if "template" not in self.args.keep:
            self.remove_template_databases()

        if "venv" not in self.args.keep:
            self.remove_venv()

        if "filestore" not in self.args.keep:
            self.remove_filestore()

        if "config" not in self.args.keep:
            self.remove_configuration()

        self.drop_database()

    def drop_database(self):
        """Drop the database if it exists."""
        if not self.database.exists:
            return logger.info(f"PostgreSQL database {self.database.name!r} does not exist, cleaning up resources")

        with style.spinner(f"Dropping database {self.database.name!r}"):
            self.database.drop()

    def remove_template_databases(self):
        pass

    def remove_venv(self):
        """Remove the venv linked to this database if not used by any other database."""
        venv = self.database.odoo_venv

        if venv is None or not venv.exists():
            return logger.debug(f"No virtual environment found for database {self.database.name!r}")

        venv_path = venv.as_posix()

        with self.database.psql("odev") as psql:
            using_venv = psql.query(
                f"""
                SELECT COUNT(*)
                FROM databases
                WHERE virtualenv = '{venv_path}'
                    AND name != '{self.database.name}'
                """
            )

        if using_venv[0][0] > 0:
            return logger.info(f"Virtual environment {venv_path} is used by other databases, keeping it")

        with style.spinner(f"Removing virtual environment {venv_path}"):
            shutil.rmtree(venv_path)

    def remove_filestore(self):
        """Remove the filestore linked to this database."""
        filestore = self.database.odoo_filestore_path

        if filestore is None or not filestore.exists():
            return logger.debug(f"No filestore found for database {self.database.name!r}")

        filestore_path = filestore.as_posix()

        with style.spinner(f"Removing filestore {filestore_path}"):
            shutil.rmtree(filestore_path)

    def remove_configuration(self):
        """Remove references to this database in the database store."""
        self.store.databases.delete(self.database)
