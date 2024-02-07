from odev.common import args
from odev.common.commands import Command
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.python import PythonEnv


logger = logging.getLogger(__name__)


class VenvCommand(Command):
    """Interact with virtual environments created and managed by Odev."""

    name = "venv"
    aliases = ["virtualenv"]

    venv_name = args.String(
        name="name",
        help="""Name of the virtual environment to activate, or a local Odoo database to select
        the virtual environment it is linked to.
        """,
    )
    command = args.String(
        help="""Python command to execute in the virtual environment.""",
        nargs="*",
    )

    def run(self):
        venv = PythonEnv(self.odev.home_path / "virtualenvs" / self.args.name)

        if not venv.exists:
            database = LocalDatabase(self.args.name)

            if database.exists:
                venv = PythonEnv(database.venv)

        if not venv.exists:
            raise self.error(f"Virtual environment {venv.path} does not exist.")

        venv.run(" ".join(self.args.command) if isinstance(self.args.command, list) else self.args.command)
