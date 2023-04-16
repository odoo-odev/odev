"""Restore a backup of a database."""

from odev.common import progress
from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class RestoreCommand(DatabaseCommand):
    """Restore a dump file on the local filesystem to a local or remote database."""

    name = "restore"
    aliases = ["upload"]

    arguments = [
        {
            "name": "backup",
            "metavar": "PATH",
            "help": "Path to the backup file to restore.",
            "action": "store_path",
        },
        {
            "name": "neutralize",
            "dest": "neutralize",
            "aliases": ["--no-clean", "--no-neutralize"],
            "action": "store_false",
            "help": """Do not neutralize the database after the dump has been restored.
            Only used on local databases.
            """,
        },
    ]

    _database_exists_required = False
    _database_allowed_platforms = ["local"]

    def run(self):
        self.check_database()
        self.restore_backup()

        if isinstance(self.database, LocalDatabase) and self.args.neutralize:
            self.odev.run_command("neutralize", database=self.database, history=False)

    def restore_backup(self):
        """Restore the backup to the selected database."""
        action: str = (
            f"file {self.args.backup.name!r} to {self.database.platform.display} database {self.database.name!r}"
        )

        with progress.spinner(f"Restoring {action}"):
            self.database.restore(file=self.args.backup)

        logger.info(f"Restored {action}")

    def check_database(self):
        """Check the target database to ensure a dump can be restored over it."""
        if isinstance(self.database, LocalDatabase):
            if self.database.exists:
                logger.warning(f"{self.database.platform.display} database {self.database.name!r} already exists")

                if not self.console.confirm("Do you want to overwrite it?", default=True):
                    raise self.error("Command aborted")

                if self.database.process.is_running:
                    with progress.spinner(f"Stopping database {self.database.process.pid}"):
                        self.database.process.kill()

                with progress.spinner(f"Removing database {self.database.name!r}"):
                    self.database.drop()

                logger.info(f"Removed database {self.database.name!r}")

            with progress.spinner(f"Creating empty database {self.database.name!r}"):
                self.database.create()

            logger.info(f"Created empty database {self.database.name!r}")
