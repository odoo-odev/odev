"""Backup a database and save its dump file locally."""

from odev.common import args
from odev.common.commands import DatabaseCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class DumpCommand(DatabaseCommand):
    """Backup a database and save its dump file on the local filesystem."""

    name = "dump"
    aliases = ["backup"]

    filestore = args.Flag(
        aliases=["-F", "--filestore"],
        help="Include the filestore when downloading the database.",
    )

    def run(self):
        """Dump the database and save its file to disk."""
        dump_path = self.database.dump(filestore=self.args.filestore)

        if dump_path is None:
            raise self.error(f"Database {self.database.name!r} could not be dumped")

        logger.info(f"Database {self.database.name!r} dumped to {dump_path}")
