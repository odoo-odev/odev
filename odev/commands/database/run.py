"""Run an Odoo database locally."""

import multiprocessing
import time

from odev.common import args, progress
from odev.common.commands import OdoobinTemplateCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class DatabaseTemplateSwapHandler(
    multiprocessing.Process
):  # TODO: check is possible/better with thread, got errors with signal when trying so
    """Handle the swapping of the template database for a running Odoo instance."""

    name = "template_pool_handler"
    daemon = True

    WAIT_TIMEOUT = 60 * 60  # 1 hour
    WAIT_DELAY = 10
    """Time to wait before checking if the template pool is restored."""

    def __init__(self, tempate_name, database_name, odev):
        super().__init__()
        self.tempate_name = tempate_name
        self.database_name = database_name
        self.odev = odev

        self._pool_size = 2
        self._pool_index = 0
        self._pool_db_is_restored = tuple(multiprocessing.Event() for _ in range(self._pool_size))

    def compute_database_name(self, pool_index=None):
        """Compute the database name based on the template name and the pool index."""
        if pool_index is None:
            pool_index = self._pool_index
        if pool_index == 0:
            return self.database_name
        else:
            return f"{self.database_name}-swap{pool_index}"

    def wait_database_ready(self):
        """Wait for the database to be ready."""
        event_to_wait = self._pool_db_is_restored[self._pool_index]
        if not event_to_wait.is_set():
            logger.info(f"Waiting for database {self.compute_database_name(self._pool_index)!r} to be ready")
        # Wait for the database to be ready before starting the Odoo instance
        self._pool_db_is_restored[self._pool_index].wait(self.WAIT_TIMEOUT)
        # Mark the previous database as not ready (will need to be restored again)
        self._pool_db_is_restored[(self._pool_index - 1) % self._pool_size].clear()
        # Increase the pool index so that next call will use the next database
        current_pool_index = self._pool_index  # store current pool index for name computation
        self._pool_index = (self._pool_index + 1) % self._pool_size  # next pool index
        return self.compute_database_name(current_pool_index)

    def run(self):
        # TODO: currently we are in a process so be careful that we shouldn't use attributes like self._pool_index
        #  as the memory is NOT shared (so it's value will stay at 0)
        while True:
            for i in range(self._pool_size):
                if self._pool_db_is_restored[i].is_set():
                    continue
                db_name = self.compute_database_name(i)
                logger.info(f"Background restoring template {self.tempate_name!r} in database {db_name!r}")
                self.odev.run_command("create", "--force", "--from-template", self.tempate_name, db_name)
                self._pool_db_is_restored[i].set()
                time.sleep(self.WAIT_DELAY)
            time.sleep(self.WAIT_DELAY)


class RunCommand(OdoobinTemplateCommand):
    """Run the odoo-bin process for the selected database locally.
    The process is run in a python virtual environment depending on the database's odoo version (as defined
    by the installed `base` module). The command takes care of installing and updating python requirements within
    the virtual environment and fetching the latest sources in the odoo standard repositories, cloning them
    if necessary. All odoo-bin arguments are passed to the odoo-bin process.
    """

    _name = "run"

    from_template = args.String(
        description="""Name of an existing PostgreSQL database to copy before running.
        If passed without a value, search for a template database with the same name as the new database.
        """
    )
    reload_template = args.Flag(
        aliases=["--reload-template", "-R"],
        description="""A few seconds after the database started,
        restore a second database with a different name from the same database template in background.
        When the first database is stopped, the second one will be used directly.
        To exit the command, use Ctrl+C (possibly multiple times).
        """,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.infer_template_instance()

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if not self.odoobin:
            raise self.error(f"Could not spawn process for database {self._database.name!r}")

        if self.odoobin.is_running:
            raise self.error(f"Database {self._database.name!r} is already running")

        if self._template:
            if not self._template.exists:
                raise self.error(f"Template database {self._template.name!r} does not exist")

            if self._database.exists:
                with progress.spinner(f"Reset database {self._database.name!r} from template {self._template.name!r}"):
                    self._database.drop()

            if self.reload_template:
                self.template_pool_handler = DatabaseTemplateSwapHandler(
                    self._template.name, self._database.name, self.odev
                )
                self.template_pool_handler.start()
                self.template_pool_handler.wait_database_ready()
            else:
                self.odev.run_command("create", "--from-template", self._template.name, self._database.name)

        self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)

        while self.reload_template:
            self._database = LocalDatabase(self.template_pool_handler.wait_database_ready())
            logger.debug(f"Reloading with database {self._database.name!r}")
            self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)

    def cleanup(self):
        if hasattr(self, "template_pool_handler"):
            self.template_pool_handler.terminate()
            self.template_pool_handler.join()
        super().cleanup()
