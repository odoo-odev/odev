"""Runs a local Odoo database."""


from odev.commands.odoo_db import create, remove
from odev.constants import DB_TEMPLATE_SUFFIX
from odev.exceptions.odoo import RunningOdooDatabase
from odev.structures import commands
from odev.utils import logging


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

    arguments = [
        {
            "aliases": ["-fv", "--force-version"],
            "type": str,
            "dest": "force_version",
            "metavar": "VERSION",
            "help": """
            Force running a specific Odoo version for the database.
            Can be useful to manually run an upgrade to a newer Odoo version.
            If not specified, the Odoo version to run is obtained from the database.
            """,
        },
    ]

    use_config_args = True

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
            create.CreateCommand.run_with(**dict(self.args.__dict__, template=template_db_name))

        self.check_database()

        if self.db_runs() and self.name == "run":
            raise RunningOdooDatabase(f"Database {self.database} is already running")

        if not self.addons:
            _logger.warning(
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise",
            )

        self.run_odoo(
            subcommand=self.odoobin_subcommand,
            additional_args=self.additional_args,
            venv_name=self.args.alt_venv and self.args.database,
            check_last_run=True,
            version=self.args.force_version,
        )

        return 0
