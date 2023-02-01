"""Kill the process of a running Odoo database."""

from odev.common.commands.database import DatabaseCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class KillCommand(DatabaseCommand):
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

    def run(self):
        """Kill the process of the current database."""
        if not self.database.exists():
            raise self.error(f"Database {self.database.name!r} does not exist")

        if not self.database.process.is_running():
            raise self.error(f"Database {self.database.name!r} is not running")

        pid = self.database.process.pid()
        logger.info(f"Killing process for running database {self.database.name!r} (pid: {pid})")
        self.database.process.kill(hard=self.args.hard)