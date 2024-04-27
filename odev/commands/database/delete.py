"""Create a new database."""

import shutil

from odev.common import args, progress, string
from odev.common.commands import LocalDatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging, silence_loggers
from odev.common.mixins import ListLocalDatabasesMixin


logger = logging.getLogger(__name__)


class DeleteCommand(ListLocalDatabasesMixin, LocalDatabaseCommand):
    """Remove a local PostgreSQL database and its associated resources.
    If no database is provided, prune all databases that are not whitelisted.
    """

    _name = "delete"
    _aliases = ["remove", "rm", "prune", "drop"]

    keep = args.List(
        aliases=["-k", "--keep"],
        default=[],
        description="""List of associated resources to keep, separated by commas. Possible values are:
        - filestore: keep the database filestore
        - template: keep template databases associated to this one
        - venv: keep the virtual environment associated to the database
        - config: keep saved attributes for the database (i.e. whitelist, saved arguments,...)
        """,
    )
    expression = args.Regex(
        aliases=["-e", "--expression"],
        description="""Regular expression pattern to filter databases to delete.
        Ignored if a database was provided.
        """,
    )
    include_whitelisted = args.Flag(
        aliases=["-w", "--include-whitelisted"],
        description="""Delete whitelisted databases as well.""",
    )

    _database_arg_required = False
    _database_exists_required = False

    def run(self):
        if self._database.exists:
            self.confirm_delete()

            with progress.spinner(f"Dropping database {self._database.name!r}"):
                return self.delete_one(self._database)

        with progress.spinner("Listing databases"):
            databases = self.list_databases(
                predicate=lambda database: (self.args.include_whitelisted or not LocalDatabase(database).whitelisted)
                and (not self.args.expression or self.args.expression.search(database))
            )

        if not databases:
            message = "No database found" if self.args.include_whitelisted else "No non-whitelisted database found"

            if self.args.expression:
                message += f" matching pattern '{self.args.expression.pattern}'"

            raise self.error(message)

        databases_list: str = string.join_and([f"{db!r}" for db in databases])
        logger.warning(f"You are about to delete the following databases: {databases_list}")

        if not self.console.confirm("Are you sure?", default=False):
            raise self.error("Command aborted")

        tracker = progress.Progress()
        task = tracker.add_task(f"Deleting {len(databases)} databases", total=len(databases))
        tracker.start()

        for database in databases:
            with silence_loggers(__name__):
                self.delete_one(LocalDatabase(database))

            tracker.update(task, advance=1)

        tracker.stop()
        logger.info(f"Deleted {len(databases)} databases")

    def confirm_delete(self) -> None:
        """Confirm the deletion of the database."""
        confirm: bool = self.console.confirm(
            f"Are you sure you want to delete the database {self._database.name!r}?",
            default=True,
        )

        if confirm and not self.args.include_whitelisted and self._database.whitelisted:
            confirm = self.console.confirm(
                f"Database {self._database.name!r} is whitelisted, are you really sure?",
                default=True,
            )

        if not confirm:
            raise self.error("Command aborted")

    def delete_one(self, database: LocalDatabase):
        """Delete a single database and its resources.
        :param database: the database to delete.
        """
        if "template" not in self.args.keep:
            self.remove_template_databases(database)

        if "venv" not in self.args.keep:
            self.remove_venv(database)

        if "filestore" not in self.args.keep:
            self.remove_filestore(database)

        if "config" not in self.args.keep:
            self.remove_configuration(database)

        self.drop_database(database)
        logger.info(f"Dropped database {database.name!r}")

    def drop_database(self, database: LocalDatabase):
        """Drop the database if it exists."""
        if not database.exists:
            return logger.info(f"PostgreSQL database {database.name!r} does not exist, cleaning up resources")

        database.drop()

    def remove_template_databases(self, database: LocalDatabase):
        pass

    def remove_venv(self, database: LocalDatabase):
        """Remove the venv linked to this database if not used by any other database."""
        if database.venv is None or not database.venv.exists:
            return logger.debug(f"No virtual environment found for database {database.name!r}")

        venv_path = database.venv.path.as_posix()

        with database.psql(self.odev.name) as psql, psql.nocache():
            using_venv = psql.query(
                f"""
                SELECT COUNT(*)
                FROM databases
                WHERE virtualenv = '{venv_path}'
                    AND name != '{database.name}'
                """
            )

        if using_venv is not None and not isinstance(using_venv, bool) and using_venv[0][0] > 0:
            return logger.info(f"Virtual environment {venv_path} is used by other databases, keeping it")

        shutil.rmtree(venv_path, ignore_errors=True)

    def remove_filestore(self, database: LocalDatabase):
        """Remove the filestore linked to this database."""
        filestore = database.filestore.path

        if filestore is None or not filestore.exists():
            return logger.debug(f"No filestore found for database {database.name!r}")

        filestore_path = filestore.as_posix()
        shutil.rmtree(filestore_path)

    def remove_configuration(self, database: LocalDatabase):
        """Remove references to this database in the database store."""
        self.store.databases.delete(database)
