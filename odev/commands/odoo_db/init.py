"""Initializes an empty PostgreSQL database for a specific Odoo version."""

import os
import re
from argparse import Namespace
from subprocess import CompletedProcess

from odev.exceptions import CommandException, InvalidArgument, InvalidQuery, InvalidVersion
from odev.structures import commands, database
from odev.utils import logging, odoo


_logger = logging.getLogger(__name__)


class InitCommand(database.DBExistsCommandMixin, commands.OdooBinMixin):
    """
    Initialize an empty PSQL database with the base version of Odoo for a given major version.
    """

    name = "init"

    arguments = [
        {
            "aliases": ["source"],
            "nargs": "?",
            "metavar": "VERSION|PATH",
            "help": """
            One of the following:
                - an Odoo version number to create and init an empty database
                - a path to an Odoo repo, all modules in there will be installed
            If nothing is specified, it's assumed the current directory is the Odoo repository.
            """,
        },
        # move positional args from OdooBinMixin after "source"
        {"name": "addons"},
        {"name": "args"},
    ]

    queries = [
        "CREATE SCHEMA unaccent_schema",
        "CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA unaccent_schema",
        "COMMENT ON EXTENSION unaccent IS 'text search dictionary that removes accents'",
        """
        CREATE FUNCTION public.unaccent(text) RETURNS text
            LANGUAGE sql IMMUTABLE
            AS $_$
                SELECT unaccent_schema.unaccent('unaccent_schema.unaccent', $1)
            $_$
        """,
        "GRANT USAGE ON SCHEMA unaccent_schema TO PUBLIC",
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        try:
            self.version = odoo.get_odoo_version(args.source or "")
            self.mode = "version"
        except InvalidVersion:
            self.path = args.source or os.getcwd()
            self.mode = "path"

        if not any(re.match(r"(-i|--install)", arg) for arg in self.additional_args):
            self.additional_args += ["-i", "base"]
        if not set(self.additional_args) & {"--st", "--stop-after-init"}:
            self.additional_args += ["--stop-after-init"]

    def run(self):
        """
        Initializes a local Odoo database with the base module then exit
        the process.
        """
        if self.db_exists():
            _logger.info(f"Database {self.database} is already initialized")
            return 0
        if self.mode == "path":
            if not odoo.is_addon_path(self.path):
                raise InvalidArgument(f"{self.path} is not a valid Odoo repository")
            self.addons.append(self.path)
            modules = odoo.list_modules(self.path)
            # Assume any module has the correct version
            try:
                self.version = odoo.get_odoo_version(odoo.get_manifest(self.path, modules[0])["version"])
            except InvalidVersion:
                raise CommandException(f"The version number on {modules[0]} is not correct")
            # Look for init argument, next one will be the list of modules to install
            for i, arg in enumerate(self.additional_args):
                if re.match(r"(-i|--install)", arg):
                    self.additional_args[i + 1] += f",{','.join(modules)}"
                    break

        odoo_result: CompletedProcess = self.run_odoo(version=self.version, capture_output=self.capture_output)
        if self.capture_output:
            self.globals_context["init_result"] = odoo_result.stdout

        result_queries = self.run_queries(self.queries)

        if not result_queries:
            raise InvalidQuery(f"An error occurred while setting up database {self.database}")

        self.config["databases"].load().set(self.database, "version_clean", self.version)

        return 0
