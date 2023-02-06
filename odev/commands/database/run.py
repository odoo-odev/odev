"""Run an Odoo database locally."""

from odev.common.commands import OdoobinCommand


class RunCommand(OdoobinCommand):
    """Run the odoo-bin process for the selected database locally."""

    name = "run"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.odoobin.is_running():
            raise self.error(f"Database {self.database.name!r} is already running")

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.odoobin.run(args=self.args.odoo_args)
