from collections.abc import Generator

from odev.common import args, progress
from odev.common.commands import Command
from odev.common.console import TableHeader
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.python import PythonEnv


logger = logging.getLogger(__name__)


class VenvCommand(Command):
    """Interact with virtual environments created and managed by Odev."""

    _name = "venv"
    _aliases = ["virtualenv"]

    _exclusive_arguments = [("command", "list", "create", "remove", "switch")]

    venv_name = args.String(
        name="name",
        description="""Name of the virtual environment to activate, or a local Odoo database to select
        the virtual environment it is linked to.
        """,
        nargs="?",
    )
    version = args.String(aliases=["-V", "--version"], description="Python version to use for the virtual environment.")
    command = args.String(
        aliases=["-c", "--command"],
        description="""Python command to execute in the context of the virtual environment.""",
    )
    action_list = args.Flag(
        name="list",
        aliases=["-l", "--list"],
        description="List virtual environments and their properties.",
    )
    action_create = args.Flag(
        name="create",
        aliases=["-C", "--create"],
        description="Create a new virtual environment.",
    )
    action_remove = args.Flag(
        name="remove",
        aliases=["-r", "--remove"],
        description="Remove an existing virtual environment.",
    )
    action_switch = args.Flag(
        name="switch",
        aliases=["-s", "--switch"],
        description="Switch the python version used by an existing virtual environment.",
    )

    def run(self):
        if self.args.list:
            self.list_venvs()
        if self.args.create:
            self.create_venv()
        if self.args.remove:
            self.remove_venv()
        if self.args.switch:
            self.switch_venv()
        if self.args.command:
            self.run_command()

    def list_venvs(self):
        """List virtual environments and their properties."""
        self.console.print()

        with progress.spinner("Listing virtual environments"):
            for venv in self.iter_venvs():
                self.table(
                    [TableHeader(min_width=20, style="bold"), TableHeader()],
                    [
                        ["Python Version", venv.version],
                        ["Interpreter Path", venv.python.as_posix()],
                    ],
                    title=venv.name,
                )

        self.console.clear_line()

    def create_venv(self):
        """Create a new virtual environment."""
        self.__check_name()
        venv = PythonEnv(self.odev.venvs_path / self.args.name, self.args.version)

        if venv.exists:
            raise self.error(f"Virtual environment {venv.name!r} already exists.")

        venv.create()

    def remove_venv(self):
        """Remove an existing virtual environment."""
        self.__check_name()
        venv = PythonEnv(self.odev.venvs_path / self.args.name)

        if not venv.exists:
            raise self.error(f"Virtual environment {venv.name!r} does not exist.")

        venv.remove()

    def switch_venv(self):
        """Switch the python version used in a virtual environment."""
        self.__check_name()

        if not self.args.version:
            raise self.error("No python version specified, use '--version' to provide one")

        venv = PythonEnv(self.odev.venvs_path / self.args.name)

        if not venv.exists:
            raise self.error(f"Virtual environment {venv.name!r} does not exist.")

        if venv.version == self.args.version:
            raise self.error(f"Virtual environment {venv.name!r} is already using Python {venv.version}")

        venv.remove()
        PythonEnv(venv.path, self.args.version).create()

    def run_command(self):
        """Run a command in the specified virtual environment."""
        self.__check_name()
        venv = PythonEnv(self.odev.venvs_path / self.args.name)

        if not venv.exists:
            venv = PythonEnv(self.args.name)

            if not venv.exists:
                database = LocalDatabase(self.args.name)

                if database.exists:
                    venv = database.venv

        if not venv.exists:
            raise self.error(f"Virtual environment {venv.name!r} does not exist.")

        venv.run(" ".join(self.args.command) if isinstance(self.args.command, list) else self.args.command)

    def __check_name(self):
        """Check if a name was properly given through CLI arguments."""
        if not self.args.name:
            raise self.error("No name specified, use '--name' to provide one")

    def iter_venvs(self) -> Generator[PythonEnv, None, None]:
        """Iterate over existing virtual environments."""
        for path in self.odev.venvs_path.iterdir():
            if path.is_dir():
                yield PythonEnv(path)
