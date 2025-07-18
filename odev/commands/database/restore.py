"""Restore a backup of a database."""


from odev.common import args, progress
from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class RestoreCommand(DatabaseCommand):
    """Restore a dump file on the local filesystem to a database.
    This will effectively replace all data in the target database.
    """

    _name = "restore"

    backup = args.Path(description="Path to the backup file to restore.")
    neutralize = args.Flag(
        aliases=["--no-neutralize"],
        default=True,
        description="""Do not neutralize the database after the dump has been restored.
        Only used on local databases.
        """,
    )

    _database_allowed_platforms = ["local"]

    @property
    def _database_exists_required(self) -> bool:
        """Return True if a database has to exist for the command to work."""
        return False

    def run(self):
        file = self.args.backup
        if not file.is_file():
            return logger.error(f"Invalid dump file {file}")

        self.check_database()
        self.restore_backup(file)
        self.neutralize_backup()

    def neutralize_backup(self):
        """Neutralize the database after the dump has been restored."""
        if isinstance(self._database, LocalDatabase) and self.args.neutralize:
            self.odev.run_command("neutralize", database=self._database, history=False)

    def restore_backup(self, file):
        """Restore the backup to the selected database."""
        action: str = f"file {file.name!r} to local database {self._database.name!r}"

        with progress.spinner(f"Restoring {action}"):
            self._database.restore(file)

        logger.info(f"Restored {action}")

    def check_database(self):
        """Check the target database to ensure a dump can be restored over it."""
        if isinstance(self._database, LocalDatabase):
            if self._database.exists:
                logger.warning(f"{self._database.platform.display} database {self._database.name!r} already exists")

                if not self.console.confirm("Do you want to overwrite it?", default=True):
                    raise self.error("Dump restoration aborted")

                if self._database.process and self._database.process.is_running:
                    with progress.spinner(f"Stopping database {self._database.process.pid}"):
                        self._database.process.kill()

                with progress.spinner(f"Removing database {self._database.name!r}"):
                    self._database.drop()

                logger.info(f"Removed database {self._database.name!r}")

            with progress.spinner(f"Creating empty database {self._database.name!r}"):
                self._database.create()

            logger.info(f"Created empty database {self._database.name!r}")
