"""Runs a local Odoo database."""

import os
import shlex
import subprocess
from argparse import ArgumentParser, Namespace

from .database import LocalDBCommand
from .. import utils
from ..cli import CommaSplitArgs


MANIFEST_NAMES = ('__manifest__.py', '__openerp__.py')


def is_addon_path(path):
    def clean(name):
        name = os.path.basename(name)
        return name

    def is_really_module(name):
        for mname in MANIFEST_NAMES:
            if os.path.isfile(os.path.join(path, name, mname)):
                return True

    return any(clean(name) for name in os.listdir(path) if is_really_module(name))


class RunScript(LocalDBCommand):
    command = "run"
    help = """
        Runs a local Odoo database, prefilling common addon paths and making
        sure the right version of Odoo is installed and in use.
        If the version of Odoo required for the database is not present, downloads it
        and installs it locally. This is done by cloning the Odoo community,
        enterprise and design-themes repositories multiple times (one per version)
        to always keep a copy of each version on the computer. To save storage space,
        only one branch is cloned per version, keeping all other branches out of
        the history. This means that the sum of the sizes of all independant
        local versions should be lower (or roughly equal if all versions are installed)
        than the size of the entire Odoo repositories.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "addons",
            action=CommaSplitArgs,
            nargs="?",
            help="Optional: comma-separated list of additional addon paths",
        )
        parser.add_argument(
            "args",
            nargs="*",
            help="Optional: additional arguments to pass to odoo-bin",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.addons = args.addons or []
        self.additional_args = args.args

    def run(self):
        """
        Runs a local Odoo database.
        """

        self.db_is_valid()

        if self.db_runs():
            raise Exception(f'Database {self.database} is already running')

        if not self.addons:
            utils.log(
                "warning",
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise",
            )

        version = self.db_version_clean()

        odoodir = os.path.join(self.config["paths"]["odoo"], version)
        odoobin = os.path.join(odoodir, "odoo/odoo-bin")

        utils.pre_run(odoodir, odoobin, version)

        addons = [
            odoodir + "/enterprise",
            odoodir + "/design-themes",
            odoodir + "/odoo/odoo/addons",
            odoodir + "/odoo/addons",
        ]
        addons.append(os.getcwd())
        addons += self.addons
        addons = [path for path in addons if is_addon_path(path)]

        python_exec = os.path.join(odoodir, "venv/bin/python")
        addons_path = ",".join(addons)
        command = shlex.join(
            [
                python_exec,
                odoobin,
                *("-d", self.database),
                f"--addons-path={addons_path}",
                *self.additional_args,
            ]
        )
        utils.log("info", f"Running:\n{command}\n")
        subprocess.run(command, shell=True, check=True)

        return 0
