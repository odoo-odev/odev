"""Create a new database."""

import re
import shutil
from typing import List, Optional, cast

from odev.common import args, progress
from odev.common.commands import OdoobinCommand
from odev.common.databases import LocalDatabase
from odev.common.odev import logger
from odev.common.odoobin import OdoobinProcess
from odev.common.version import OdooVersion


TEMPLATE_SUFFIX = ":template"


class CreateCommand(OdoobinCommand):
    """Create a new Odoo database locally, or copy an existing database template."""

    _name = "create"
    _aliases = ["init"]

    template_argument = args.String(
        name="template",
        aliases=["-t", "--template"],
        description="Name of an existing PostgreSQL database to copy.",
    )
    new_template = args.Flag(
        aliases=["-T", "--create-template"],
        description=f"Create the database as a template to reuse later (append {TEMPLATE_SUFFIX!r} to its name).",
    )
    copy_filestore = args.Flag(
        aliases=["--no-filestore"],
        description="Do not copy the filestore from the template.",
        default=True,
    )
    bare = args.Flag(
        aliases=["--bare", "--no-init"],
        description="Do not initialize the database (create the PostgreSQL database then exit).",
    )
    version_argument = args.String(
        name="version",
        description="""The Odoo version to use for the new database.
        If not specified and a template is provided, the version of
        the template database will be used. Otherwise, the version will default to "master".
        """,
    )

    _database_exists_required = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if self.args.template and self.args.new_template:
            raise self.error("The arguments `template` and `new_template` are mutually exclusive")

        if self.args.new_template:
            self.args.database += TEMPLATE_SUFFIX
            self._database = LocalDatabase(self.args.database)

        if self.args.template:
            self.template: Optional[LocalDatabase] = LocalDatabase(self.args.template + TEMPLATE_SUFFIX)
            """Template database to copy."""

            if not self.template.exists:
                self.template = LocalDatabase(self.args.template)
        else:
            self.template = None

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

        if self.args.bare or self.template is not None:
            return

        self.initialize_database()

    def ensure_database_not_exists(self):
        """Drop the database if it exists."""
        with self._database.psql().nocache():
            if self._database.exists:
                logger.warning(f"Database {self._database.name!r} already exists")

                if not self.console.confirm("Overwrite it?", default=True):
                    raise self.error(f"Cannot create database with an already existing name {self._database.name!r}")

                with progress.spinner(f"Dropping database {self._database.name!r}"):
                    self._database.drop()

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
        fs_template = cast(LocalDatabase, self.template).filestore.path
        fs_database = self._database.filestore.path

        if fs_template is not None and fs_template.exists() and fs_database is not None:
            if fs_database.exists():
                logger.warning(f"Filestore for {self._database.name!r} already exists")

                if not self.console.confirm("Overwrite it?", default=True):
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
        message = f"database {self._database.name!r}" + (f" from template {template!r}" if template else "")

        if self.template and self.template.connector:
            self.template.connector.disconnect()

        with progress.spinner(f"Creating {message}"):
            created = self._database.create(template=template) & self._database.unaccent()

            if created is False:
                raise self.error(f"Failed to create database {self._database.name!r}")

        logger.info(f"Created {message}")

    def initialize_database(self) -> None:
        """Initialize the database."""
        if self.template:
            logger.debug(f"Initializing database {self._database.name!r} from template {self.template.name!r}")

        args: List[str] = self.args.odoo_args
        joined_args = " ".join(args)

        if not re.search(r"(-i|--install)", joined_args):
            args.extend(["--init", "base"])

        if not re.search(r"--st(op-after-init)?", joined_args):
            args.append("--stop-after-init")

        process = self.odoobin or OdoobinProcess(self._database)
        process.with_edition("enterprise" if self.args.enterprise else "community")
        process.with_version(self.version)
        process.with_venv(self.venv)

        process.run(args=args, progress=self.odoobin_progress)

        if process is None:
            raise self.error(f"Failed to initialize database {self._database.name!r}")

        logger.info(f"Initialized database {self._database.name!r}")
