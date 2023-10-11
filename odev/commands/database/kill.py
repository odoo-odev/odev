"""Kill the process of a running Odoo database."""

from time import sleep

from odev.common import progress
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
        with progress.spinner(f"Killing process for running database {self.database.name!r} (pid: {self.odoobin.pid})"):
            self.odoobin.kill(hard=self.args.hard)

            # Wait for up to 3 seconds total with 5 retries until the process is gone
            retries: int = 0
            while self.odoobin.is_running and retries < 5:
                retries += 1
                sleep(0.2 * retries)

            if self.odoobin.is_running:
                logger.warn(
                    f"Database {self.database.name!r} (pid: {self.odoobin.pid}) is still running, force-killing it"
                )
                self.odoobin.kill(hard=True)
