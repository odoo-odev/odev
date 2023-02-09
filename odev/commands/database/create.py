"""Create a new database."""

import re
import shutil
from typing import List, Optional

from odev.common import prompt, style
from odev.common.commands import OdoobinCommand
from odev.common.databases import PostgresDatabase
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
            "nargs": "?",
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
            "aliases": ["-b", "--bare", "--no-init"],
            "action": "store_true",
            "help": "Do not initialize the database (create the SQL database then exit).",
        },
        {
            "name": "version",
            "aliases": ["-V", "--version"],
            "help": """The Odoo version to use for the new database.
            If not specified, the version of the template database will be used.
            """,
        },
    ]

    _require_exists = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template: Optional[PostgresDatabase] = self.args.template and PostgresDatabase(self.args.template) or None
        """Template database to copy."""

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
        if self.database.exists():
            logger.warning(f"Database {self.database.name!r} already exists")

            if not prompt.confirm("Overwrite it?"):
                raise self.error(f"Cannot create database with already existing name {self.database.name!r}")

            with style.spinner(f"Dropping database {self.database.name!r}"):
                self.database.drop()

    def ensure_template_exists(self):
        """Ensure the template database exists."""
        if self.template is None:
            return

        if not self.template.exists():
            raise self.error(f"Template database {self.template.name!r} does not exist")

        if self.template.process is not None and self.template.process.is_running():
            raise self.error(f"Cannot copy template {self.template.name!r} while it is running, shut it down and retry")

    def copy_template_filestore(self):
        """Copy the template filestore to the new database."""
        with self.template:
            template_filestore = self.template.odoo_filestore_path()

        if template_filestore is not None and template_filestore.exists():
            database_filestore = self.database._odoo_filestore_path()

            if database_filestore is not None:
                if database_filestore.exists():
                    logger.warning(f"Filestore for {self.database.name!r} already exists")

                    if not prompt.confirm("Overwrite it?"):
                        raise self.error(f"Cannot copy template filestore to existing directory {database_filestore!s}")

                    with style.spinner(f"Removing {database_filestore!s}"):
                        shutil.rmtree(database_filestore)

                with style.spinner(f"Copying filestore from {template_filestore!s} to {database_filestore!s}"):
                    database_filestore.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(template_filestore, database_filestore)

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

        with style.spinner(f"Creating {message}"):
            created = self.database.create(template=template)

            if created is False:
                raise self.error(f"Failed to create database {self.database.name!r}")

            unaccent_queries = [
                "CREATE SCHEMA IF NOT EXISTS unaccent_schema",
                "CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA unaccent_schema",
                "COMMENT ON EXTENSION unaccent IS 'text search dictionary that removes accents'",
                """
                DO $$
                BEGIN
                    CREATE FUNCTION public.unaccent(text)
                        RETURNS text
                        LANGUAGE sql IMMUTABLE
                        AS $_$
                            SELECT unaccent_schema.unaccent('unaccent_schema.unaccent', $1)
                        $_$;
                    EXCEPTION
                        WHEN duplicate_function
                        THEN null;
                END; $$
                """,
                "GRANT USAGE ON SCHEMA unaccent_schema TO PUBLIC",
            ]

            with self.database:
                for query in unaccent_queries:
                    self.database.query(query)

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

        version = OdooVersion(self.args.version) if self.args.version else None

        init_process = (self.odoobin or OdooBinProcess(self.database)).with_version(version).run(args=args, stream=True)

        if init_process is None:
            raise self.error(f"Failed to initialize database {self.database.name!r}")

        logger.info(f"Initialized database {self.database.name!r}")
