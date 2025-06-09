"""Run an Odoo database locally."""


from odev.common import args, progress
from odev.common.commands import OdoobinTemplateCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.infer_template_instance()

    @property
    def _database_exists_required(self) -> bool:
        """Return True if a database has to exist for the command to work."""
        return not bool(self.from_template)

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if self._template:
            if not self._template.exists:
                raise self.error(f"Template database {self._template.name!r} does not exist")

            if self._database.exists:
                with progress.spinner(f"Reset database {self._database.name!r} from template {self._template.name!r}"):
                    self._database.drop()

            self.odev.run_command("create", "--from-template", self._template.name, self._database.name)

        if not self.odoobin:
            raise self.error(f"Could not spawn process for database {self._database.name!r}")

        if self.odoobin.is_running:
            raise self.error(f"Database {self._database.name!r} is already running")

        self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)
