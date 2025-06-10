"""Deploy a local module to a database through the module import feature."""

import re

from odev.common import args
from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase, RemoteDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess


logger = logging.getLogger(__name__)


class DeployCommand(DatabaseCommand):
    """Deploy a local module to a database through the module import feature.
    Requires the 'base_import_module' module to be installed on the database,
    and the database to be running.
    """

    _name = "deploy"

    module = args.Path(description="Path to the module to deploy (must be a valid Odoo module).")
    odoo_args = args.String(description="Additional arguments to pass to odoo-bin deploy.", nargs="*...")

    def run(self):
        if not self._database.running:
            raise self.error(
                f"{self._database.platform.display} database {self._database.name!r} must be running to deploy a module"
            )

        odoobin: OdoobinProcess = (
            self._database.process
            if isinstance(self._database, LocalDatabase)
            else OdoobinProcess(LocalDatabase(self.odev.name), version=self._database.version)
        )

        url = self._database.url if isinstance(self._database, RemoteDatabase) else None

        process = odoobin.deploy(
            url=url,
            module=self.args.module,
            args=self.args.odoo_args,
        )

        if process is None or process.stdout is None:
            return None

        result = process.stdout.decode()
        error_match = re.search(r"\nError", result, re.IGNORECASE)

        if error_match is not None:
            raise self.error(result[error_match.start() + 1 :])

        logger.info(f"Successfully deployed module {self.args.module.name!r} to database {self._database.name!r}")
