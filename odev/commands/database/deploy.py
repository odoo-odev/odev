"""Deploy a local module to a database through the module import feature."""

import re

from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoo import OdoobinProcess


logger = logging.getLogger(__name__)


class DeployCommand(DatabaseCommand):
    """Deploy a local module to a database through the module import feature.
    Requires the 'base_import_module' module to be installed on the database,
    and the database to be running.
    """

    name = "deploy"

    arguments = [
        {
            "name": "module",
            "help": "Path to the module to deploy (must be a valid Odoo module).",
            "action": "store_path",
        },
        {
            "name": "odoo_args",
            "nargs": "*...",
            "help": "Additional arguments to pass to odoo-bin deploy.",
        },
    ]

    def run(self):
        if not self.database.running:
            raise self.error(
                f"{self.database.platform.display} database {self.database.name!r} must be running to deploy a module"
            )

        odoobin: OdoobinProcess = OdoobinProcess(LocalDatabase(self.odev.name), version=self.database.version)
        process = odoobin.deploy(
            url=self.database.url,
            module=self.args.module,
            args=self.args.odoo_args,
        )

        if process is None or process.stdout is None:
            return None

        result = process.stdout.decode()
        error_match = re.search(r"\nError", result, re.IGNORECASE)

        if error_match is not None:
            raise self.error(result[error_match.start() + 1 :])

        logger.info(f"Successfully deployed module {self.args.module.name!r} to database {self.database.name!r}")