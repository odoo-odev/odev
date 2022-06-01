"""Runs a local Odoo database."""

import os
import re
import shlex
import subprocess
from argparse import Namespace
from datetime import datetime

from odev.commands.odoo_db import remove
from odev.constants import DB_TEMPLATE_SUFFIX, ODOO_ADDON_PATHS
from odev.exceptions.odoo import RunningOdooDatabase
from odev.structures import actions, commands
from odev.utils import logging, odoo
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


class RunCommand(commands.TemplateDBCommand, commands.OdooBinMixin):
    """
    Run a local Odoo database, prefilling common addon paths and making
    sure the right version of Odoo is installed and in use.

    If the version of Odoo required for the database is not present, download and install it locally.
    This is done by cloning the Odoo community, enterprise and design-themes repositories
    multiple times (once per version) to always keep a copy of each version on the computer.
    To save storage space, only one branch is cloned per version, keeping all other branches out of
    the history.
    """

    name = "run"

    odoobin_mixin_args = [x for x in commands.OdooBinMixin.arguments if x.get("name") == "args"]

    arguments = [
        {
            "aliases": ["-s", "--save"],
            "dest": "save",
            "action": "store_true",
            "help": "Save the current arguments for next calls",
        },
        {
            "aliases": ["-e", "--env"],
            "dest": "alt_venv",
            "action": "store_true",
            "help": "Create an alternative venv (database name)",
        },
        {
            "name": "addons",
            "action": actions.CommaSplitAction,
            "nargs": "?",
            "help": "Comma-separated list of additional addon paths",
        },
    ] + odoobin_mixin_args

    odoobin_subcommand = None
    """
    Optional subcommand to pass to `odoo-bin` at execution time.
    """

    force_save_args = False
    """
    Whether to force re-saving arguments to the database's config
    within subcommands.
    """

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.config_args_key = f"args_{self.name}"
        config_args = list(
            filter(lambda s: s, self.config["databases"].get(self.database, self.config_args_key, "").split(" "))
        )

        self.addons = args.addons or ([config_args.pop(0)] if config_args[:1] and os.path.isdir(config_args[0]) else [])
        self.additional_args = args.args or config_args

        if args.save and (
            not config_args
            or _logger.confirm("Arguments have already been saved for this database, do you want to override them?")
        ):
            self.force_save_args = True
            self.config["databases"].set(
                self.database,
                self.config_args_key,
                shlex.join([*self.addons, *self.additional_args]),
            )

    def run(self):
        """
        Runs a local Odoo database.
        """

        if self.args.from_template:
            template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"
            self.check_database(template_db_name)

            if self.db_exists(self.database):
                _logger.info("The old database will be deleted to restore the template")
                remove.RemoveCommand.run_with(**dict(self.args.__dict__, keep_template=bool(self.args.from_template)))

            _logger.warning(f"Restoring the template {template_db_name}")
            self.run_queries(
                f'CREATE DATABASE "{self.database}" WITH TEMPLATE "{template_db_name}"', f"{template_db_name}"
            )

        self.check_database()

        if self.db_runs() and self.name == "run":
            raise RunningOdooDatabase(f"Database {self.database} is already running")

        if not self.addons:
            _logger.warning(
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise",
            )

        version = self.db_version_clean()

        repos_path = self.config["odev"].get("paths", "odoo")
        version_path = odoo.repos_version_path(repos_path, version)
        odoobin = os.path.join(version_path, "odoo/odoo-bin")
        venv_name = (
            self.database if self.args.alt_venv or os.path.isdir(os.path.join(version_path, self.database)) else "venv"
        )

        odoo.prepare_odoobin(repos_path, version, skip_prompt=self.args.pull, venv_name=venv_name)

        addons = [version_path + addon_path for addon_path in ODOO_ADDON_PATHS]
        addons += [os.getcwd(), *self.addons]
        addons = [path for path in addons if odoo.is_addon_path(path)]

        if (
            any(re.compile(r"^(-i|--install|-u|--update)").match(arg) for arg in self.additional_args)
            or not self.config["databases"].get(self.database, "lastrun", False)
            or self.args.alt_venv
        ):
            odoo.prepare_requirements(repos_path, version, venv_name=venv_name, addons=addons)

        python_exec = os.path.join(version_path, f"{venv_name}/bin/python")
        addons_path = ",".join(addons)
        command_args = [
            python_exec,
            odoobin,
            *("-d", self.database),
            f"--addons-path={addons_path}",
            *self.additional_args,
        ]

        if self.odoobin_subcommand:
            command_args.insert(2, self.odoobin_subcommand)

        self.config["databases"].set(
            self.database,
            "lastrun",
            datetime.now().strftime("%a %d %B %Y, %H:%M:%S"),
        )

        command = shlex.join(command_args)
        _logger.info(f"Running: {command}")

        with capture_signals():
            subprocess.run(command, shell=True, check=True)

        return 0
