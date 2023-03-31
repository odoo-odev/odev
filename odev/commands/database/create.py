"""Create a new database."""

import re
import shutil
from typing import List, Optional

from odev.common import progress
from odev.common.commands import OdoobinCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoo import OdooBinProcess
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class CreateCommand(OdoobinCommand):
    """Create a new Odoo database locally, restoring templates and dumps on the fly."""

    name = "create"
    aliases = ["init"]
    arguments = [
        {
            "name": "template",
            "aliases": ["-t", "--template"],
            "help": "Name of an existing PostgreSQL database to copy.",
        },
        {
            "name": "copy_filestore",
            "dest": "copy_filestore",
            "aliases": ["--no-filestore"],
            "action": "store_false",
            "help": "Do not copy the filestore from the template.",
        },
        {
            "name": "bare",
            "aliases": ["--bare", "--no-init"],
            "action": "store_true",
            "help": "Do not initialize the database (create the SQL database then exit).",
        },
        {
            "name": "version",
            "help": """The Odoo version to use for the new database.
            If not specified and a template is provided, the version of
            the template database will be used. Otherwise, the version will default to "master".
            """,
        },
    ]

    _database_exists_required = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template: Optional[LocalDatabase] = LocalDatabase(self.args.template) if self.args.template else None
        """Template database to copy."""

        version = self.args.version and OdooVersion(self.args.version) or None
        """Odoo version to use for the new database."""

        if version is None and self.template is not None:
            with self.template:
                version = self.template.version

        if version is None:
            version = OdooVersion("master")

        self.version: OdooVersion = version
        """Odoo version to use for the new database."""

    def run(self):
        """Create a new database locally."""
        self.create_database()

        if self.args.copy_filestore and self.template is not None:
            self.copy_template_filestore()

        if self.args.bare:
            return

        self.initialize_database()

    def ensure_database_not_exists(self):
        """Drop the database if it exists."""
        if self.database.exists:
            logger.warning(f"Database {self.database.name!r} already exists")

            if not self.console.confirm("Overwrite it?"):
                raise self.error(f"Cannot create database with already existing name {self.database.name!r}")

            with progress.spinner(f"Dropping database {self.database.name!r}"):
                self.database.drop()

    def ensure_template_exists(self):
        """Ensure the template database exists."""
        if self.template is None:
            return

        if not self.template.exists:
            raise self.error(f"Template database {self.template.name!r} does not exist")

        if self.template.process is not None and self.template.process.is_running:
            raise self.error(f"Cannot copy template {self.template.name!r} while it is running, shut it down and retry")

    def copy_template_filestore(self):
        """Copy the template filestore to the new database."""
        fs_template = self.template.filestore.path
        fs_database = self.database.filestore.path

        if fs_template is not None and fs_template.exists() and fs_database is not None:
            if fs_database.exists():
                logger.warning(f"Filestore for {self.database.name!r} already exists")

                if not self.console.confirm("Overwrite it?"):
                    raise self.error(f"Cannot copy template filestore to existing directory {fs_database!s}")

                with progress.spinner(f"Removing {fs_database!s}"):
                    shutil.rmtree(fs_database)

            with progress.spinner(f"Copying filestore from {fs_template!s} to {fs_database!s}"):
                fs_database.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(fs_template, fs_database)

    def create_database(self):
        """Create the database and copy the template if needed.
        Enable unaccent extension on the new database.
        """
        self.ensure_database_not_exists()
        self.ensure_template_exists()

        template = self.template.name if self.template else None
        message = f"database {self.database.name!r}" + (f" from template {template!r}" if template else "")

        if self.template:
            self.template.connector.disconnect()

        with progress.spinner(f"Creating {message}"):
            created = self.database.create(template=template) & self.database.unaccent()

            if created is False:
                raise self.error(f"Failed to create database {self.database.name!r}")

        logger.info(f"Created {message}")

    def initialize_database(self):
        """Initialize the database."""
        if self.template:
            logger.debug(f"Initializing database {self.database.name!r} from template {self.template.name!r}")

        args: List[str] = self.args.odoo_args
        joined_args = " ".join(args)

        if not re.search(r"(-i|--install)", joined_args):
            args.extend(["--init", "base"])

        if not re.search(r"--st(op-after-init)?", joined_args):
            args.append("--stop-after-init")

        process = (self.odoobin or OdooBinProcess(self.database)).with_version(self.version).run(args=args, stream=True)

        if process is None:
            raise self.error(f"Failed to initialize database {self.database.name!r}")

        logger.info(f"Initialized database {self.database.name!r}")
