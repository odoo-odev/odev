"""Kill the process of a running Odoo database."""

from odev.common.commands import OdoobinCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class KillCommand(OdoobinCommand):
    """Kill a running Odoo database. Useful if the process crashed because of
    a forgotten IPDB or if you lost your terminal and don't want to search
    for the process' PID.
    """

    name = "kill"

    arguments = [
        {
            "name": "hard",
            "aliases": ["-H", "--hard"],
            "action": "store_true",
            "help": "Kill the database process with SIGKILL instead of SIGINT.",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.odoobin.is_running:
            raise self.error(f"Database {self.database.name!r} is not running")

    def run(self):
        """Kill the process of the current database."""
        logger.info(f"Killing process for running database {self.database.name!r} (pid: {self.odoobin.pid})")
        self.odoobin.kill(hard=self.args.hard)
