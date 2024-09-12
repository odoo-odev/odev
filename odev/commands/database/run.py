"""Run an Odoo database locally."""

from typing import Optional

from odev.commands.database.create import TEMPLATE_SUFFIX
from odev.common import args, progress
from odev.common.commands import OdoobinCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class RunCommand(OdoobinCommand):
    """Run the odoo-bin process for the selected database locally.
    The process is run in a python virtual environment depending on the database's odoo version (as defined
    by the installed `base` module). The command takes care of installing and updating python requirements within
    the virtual environment and fetching the latest sources in the odoo standard repositories, cloning them
    if necessary. All odoo-bin arguments are passed to the odoo-bin process.
    """

    _name = "run"

    from_template = args.String(
        name="template",
        aliases=["-t", "--template"],
        description="Name of an existing PostgreSQL database to copy before running.",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if self.args.template:
            self.template: Optional[LocalDatabase] = LocalDatabase(self.args.template + TEMPLATE_SUFFIX)
            """Template database to copy."""

            if not self.template.exists:
                self.template = LocalDatabase(self.args.template)
        else:
            self.template = None

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if not self.odoobin:
            raise self.error(f"Could not spawn process for database {self._database.name!r}")

        if self.odoobin.is_running:
            raise self.error(f"Database {self._database.name!r} is already running")

        if self.template:
            if not self.template.exists:
                raise self.error(f"Template database {self.template.name!r} does not exist")

            if self._database.exists:
                with progress.spinner(f"Reset database {self._database.name!r} from template {self.template.name!r}"):
                    self._database.drop()

            self.odev.run_command("create", self._database.name, "--template", self.template.name)

        self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)
