"""Initializes an empty PostgreSQL database for a specific Odoo version."""

import re
from argparse import Namespace
from subprocess import CompletedProcess

from odev.exceptions import InvalidArgument, InvalidQuery, InvalidVersion
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
            "name": "version",
            "help": "Odoo version to use; must match an Odoo community branch",
        },
        # move positional args from OdooBinMixin after "version"
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
            self.version = odoo.get_odoo_version(args.version)
        except InvalidVersion as exc:
            raise InvalidArgument(str(exc)) from exc

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

        odoo_result: CompletedProcess = self.run_odoo(version=self.version, capture_output=self.capture_output)
        if self.capture_output:
            self.globals_context["init_result"] = odoo_result.stdout

        result_queries = self.run_queries(self.queries)

        if not result_queries:
            raise InvalidQuery(f"An error occurred while setting up database {self.database}")

        self.config["databases"].set(self.database, "version_clean", self.version)

        return 0
