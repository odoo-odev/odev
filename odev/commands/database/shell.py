"""Run an Odoo database locally."""

from odev.common.commands import OdoobinCommand


class ShellCommand(OdoobinCommand):
    """Run the odoo-bin process in shell mode for the selected database locally."""

    name = "shell"

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.odoobin.run(args=self.args.odoo_args, subcommand=self.name)
