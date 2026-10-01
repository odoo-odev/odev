"""List the Odoo modules contained in a directory."""

from pathlib import Path

from odev.common import args
from odev.common.commands import Command
from odev.common.odoobin import OdoobinProcess


class ListModulesCommand(Command):
    """Print the comma-separated list of the Odoo modules found in a directory.

    Modules are looked up recursively, including in subdirectories and git submodules. The output can be passed
    as is to the `-i` or `-u` options of odoo-bin.
    """

    _name = "list-modules"
    _aliases = ["modules"]

    path = args.Path(
        nargs="?",
        description="Directory to search for Odoo modules, defaults to the current directory.",
    )

    def run(self):
        """Print the names of the modules found in the directory."""
        path = self.args.path or Path().resolve()

        if not path.is_dir():
            raise self.error(f"Path {path.as_posix()!r} is not a directory")

        modules = OdoobinProcess.list_addons([path])

        if not modules:
            raise self.error(f"No Odoo module found in {path.as_posix()!r}")

        self.print(",".join(modules), highlight=False, soft_wrap=True)
