from abc import ABC
from pathlib import Path

from odev.common.commands import DatabaseCommand
from odev.common.databases import PostgresDatabase
from odev.common.logging import logging
from odev.common.odoo import OdooBinProcess


logger = logging.getLogger(__name__)


class OdoobinCommand(DatabaseCommand, ABC):
    """Base class for commands that interact with an odoo-bin process."""

    database: PostgresDatabase
    arguments = [
        {
            "name": "addons",
            "nargs": "?",
            "action": "store_comma_split",
            "help": """Comma-separated list of additional addon paths.
            The standard Odoo addons paths are automatically added to the odoo-bin command (including enterprise
            if any enterprise module is installed). If this command is run from within an Odoo addons directory
            and no additional addons are specified, the current directory will be added to the list of addons.
            """,
        },
        {
            "name": "odoo_args",
            "nargs": "...",
            "help": """Additional arguments to pass to odoo-bin; Check the documentation at
            https://www.odoo.com/documentation/16.0/fr/developer/cli.html
            for the list of available arguments.
            """,
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.database, PostgresDatabase):
            raise ValueError("Database must be an instance of PostgresDatabase.")

        self.odoobin: OdooBinProcess = self.database.process
        """The odoo-bin process associated with the database."""

        if self.args.addons is not None:
            addons_paths = [Path(addon).resolve() for addon in self.args.addons]
            invalid_paths = [path for path in addons_paths if not self.odoobin.check_addons_path(path)]

            if invalid_paths:
                logger.warning(
                    "Some additional addons paths are invalid, they will be ignored:\n"
                    + "\n".join(path.as_posix() for path in invalid_paths)
                )
        else:
            addons_paths = [Path().resolve()]

        self.odoobin.additional_addons_paths = addons_paths
        """Additional addons paths to pass to odoo-bin."""