"""Initializes an empty PostgreSQL database for a specific Odoo version."""

import os
import re
import shlex
import subprocess
from argparse import Namespace

from packaging.version import Version

from odev.constants.odoo import ODOO_ADDON_PATHS, OPENERP_ADDON_PATHS
from odev.exceptions import InvalidArgument, InvalidQuery, InvalidVersion
from odev.structures import commands, database
from odev.utils import logging, odoo
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


class InitCommand(database.DBExistsCommandMixin, commands.OdooBinMixin):
    """
    Initialize an empty PSQL database with the base version of Odoo for a given major version.
    """

    name = "init"

    odoobin_mixin_args = [x for x in commands.OdooBinMixin.arguments if x.get("name") == "args"]

    arguments = [
        {
            "aliases": ["version"],
            "help": "Odoo version to use; must match an Odoo community branch",
        },
    ] + odoobin_mixin_args

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
        self.version = args.version
        self.additional_args = args.args
        self.args.addons = self.args.addons if "addons" in self.args and self.args.addons else []

    def run(self):
        """
        Initializes a local Odoo database with the base module then exit
        the process.
        """

        # FIXME: DRY "run odoo-bin code" across run/init/cloc commands

        if self.db_exists():
            _logger.info(f"Database {self.database} is already initialized")
            return 0

        try:
            version = odoo.get_odoo_version(self.version)
        except InvalidVersion as exc:
            raise InvalidArgument(str(exc)) from exc

        pre_openerp_refactor = self.db_version_parsed() >= Version("9.13")

        repos_path = self.config["odev"].get("paths", "odoo")
        version_path = odoo.repos_version_path(repos_path, version)
        odoobin = os.path.join(version_path, ("odoo/odoo-bin" if pre_openerp_refactor else "odoo/odoo.py"))

        odoo.prepare_odoobin(repos_path, version, skip_prompt=self.args.pull)

        common_addons = ODOO_ADDON_PATHS if pre_openerp_refactor else OPENERP_ADDON_PATHS
        addons = [version_path + addon_path for addon_path in common_addons] + self.args.addons
        addons = [path for path in addons if odoo.is_addon_path(path)]
        odoo.prepare_requirements(repos_path, version, addons=addons)

        python_exec = os.path.join(version_path, "venv/bin/python")
        addons_path = ",".join(addons)

        if not any(re.compile(r"^(-i|--install)").match(arg) for arg in self.additional_args):
            self.additional_args += ["-i", "base"]

        command = shlex.join(
            [
                python_exec,
                odoobin,
                *("-d", self.database),
                f"--addons-path={addons_path}",
                "--stop-after-init",
                *self.additional_args,
            ]
        )
        _logger.info(f"Running: {command}")

        result = 0

        with capture_signals():
            if self.capture_output:
                self.globals_context["init_result"] = subprocess.getoutput(command)
            else:
                subprocess.run(command, shell=True, check=True)

        result_queries = self.run_queries(self.queries)

        if not result_queries:
            raise InvalidQuery(f"An error occurred while setting up database {self.database}")

        self.config["databases"].set(self.database, "version_clean", version)

        return result
