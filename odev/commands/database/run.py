"""Run an Odoo database locally."""

from odev.common.commands import OdoobinCommand


class RunCommand(OdoobinCommand):
    """Run the odoo-bin process for the selected database locally."""

    name = "run"

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.odoobin.run(args=self.args.odoo_args)
