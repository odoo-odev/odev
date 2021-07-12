"""Initializes an empty PostgreSQL database for a specific Odoo version."""

import os
import re
import shlex
import subprocess
from argparse import ArgumentParser, Namespace

from .database import LocalDBCommand
from .. import utils


re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')


class InitScript(LocalDBCommand):
    command = "init"
    help = """
        Initializes an empty PSQL database with a basic version of Odoo.
        Basically, installs the base module on an empty DB.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "version",
            help="Odoo version to use; must correspond to an Odoo community branch",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.version = args.version

    def run(self):
        """
        Initializes a local Odoo database with the base module then exit
        the process.
        """

        if not self.db_exists_all():
            raise Exception(f"Database {self.database} does not exist")

        if self.db_exists():
            return 0

        try:
            match = re_version.match(self.version)
            version = match.group(0)
        except Exception:
            raise Exception(f'Invalid version number "{self.version}"')

        odoodir = os.path.join(self.config["paths"]["odoo"], version)
        odoobin = os.path.join(odoodir, "odoo/odoo-bin")

        utils.pre_run(odoodir, odoobin, version)

        addons = [
            odoodir + "/enterprise",
            odoodir + "/design-themes",
            odoodir + "/odoo/odoo/addons",
            odoodir + "/odoo/addons",
        ]

        python_exec = os.path.join(odoodir, "venv/bin/python")
        addons_path = ",".join(addons)
        command = shlex.join(
            [
                python_exec,
                odoobin,
                *("-d", self.database),
                f"--addons-path={addons_path}",
                "-i base",
                "--stop-after-init",
                "--without-demo=all",
            ]
        )
        utils.log("info", f"Running:\n{command}\n")
        subprocess.run(command, shell=True, check=True)

        return 0
