import re
from abc import ABC
from pathlib import Path
from typing import Optional

from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoo import OdooBinProcess
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class OdoobinCommand(DatabaseCommand, ABC):
    """Base class for commands that interact with an odoo-bin process."""

    database: LocalDatabase
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
        {
            "name": "enterprise",
            "aliases": ["-e", "--enterprise"],
            "action": "store_true",
            "help": "Force running the database with enterprise addons.",
        },
        {
            "name": "version",
            "aliases": ["-V", "--version"],
            "help": """The Odoo version to use for running the database.
            If not specified, defaults to the latest version of the base module installed in the database.
            """,
        },
    ]

    _database_allowed_platforms = ["local"]

    _odoo_log_regex: re.Pattern = re.compile(
        r"""
            (?:
                (?P<date>\d{4}-\d{2}-\d{2})\s
                (?P<time>\d{2}:\d{2}:\d{2},\d{3})\s
                (?P<pid>\d+)\s
                (?P<level>[A-Z]+)\s
                (?P<database>[^\s]+)\s
                (?P<logger>[^:]+):\s
                (?P<description>.*)
            )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    """Regular expression to match the output of odoo-bin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.database, LocalDatabase):
            raise self.error(f"Database must be an instance of {LocalDatabase.__name__}.")

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

        if self.odoobin is not None:
            self.odoobin.additional_addons_paths = addons_paths
            self.odoobin._force_enterprise = bool(self.args.enterprise)

            if self.args.version is not None:
                self.odoobin._version = OdooVersion(self.args.version)

    @property
    def odoobin(self) -> Optional[OdooBinProcess]:
        """The odoo-bin process associated with the database."""
        return self.database.process
