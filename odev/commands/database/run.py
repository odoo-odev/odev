"""Run an Odoo database locally."""

from odev.common.commands.database import DatabaseCommand


class RunCommand(DatabaseCommand):
    """Run the odoo-bin process for the selected database locally."""

    name = "run"

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.database.process.run()
