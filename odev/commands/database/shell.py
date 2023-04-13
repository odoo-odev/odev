"""Run an Odoo database locally."""

from odev.common.commands import OdoobinShellCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class ShellCommand(OdoobinShellCommand):
    """Run the odoo-bin process in shell mode for the selected database locally."""

    name = "shell"
