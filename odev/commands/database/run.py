"""Run an Odoo database locally."""

from odev.common.commands import OdoobinCommand
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.odoobin.is_running:
            raise self.error(f"Database {self._database.name!r} is already running")

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)
