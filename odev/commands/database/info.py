"""Display information about a local or remote database."""

import re
from typing import Any, List, MutableMapping

from odev.common import string
from odev.common.commands import DatabaseCommand
from odev.common.console import Colors
from odev.common.databases import LocalDatabase, SaasDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DISPLAY_NA = "N/A"
DISPLAY_NEVER = "Never"
DISPLAY_TRUE = f"[bold {Colors.GREEN}]✔[bold {Colors.GREEN}]"
DISPLAY_FALSE = f"[bold {Colors.RED}]❌[bold {Colors.RED}]"

TABLE_HEADERS: List[MutableMapping[str, Any]] = [
    {"name": "", "style": "bold", "min_width": 15},
    {"name": ""},
]


class InfoCommand(DatabaseCommand):
    """Fetch and display information about a database."""

    name = "info"
    aliases = ["i"]

    def run(self):
        if isinstance(self.database, LocalDatabase) and not self.database.is_odoo:
            raise self.error(f"Database '{self.database.name}' is not an Odoo database")

        return self.print_info()

    def print_info(self):
        """Print information about the database."""

        self.print_table(
            self.info_table_rows_base(),
            self.database.name.upper(),
            style=f"bold {Colors.PURPLE}",
        )

        self.print_table(self.info_table_rows_database(), "Database")

        if isinstance(self.database, LocalDatabase):
            self.print_table(
                self.info_table_rows_local(),
                self.database.platform.display,
            )

        elif isinstance(self.database, SaasDatabase):
            self.print_table(
                self.info_table_rows_saas(),
                self.database.platform.display,
            )

    def print_table(self, rows: List[List[str]], name: str = None, style: str = None):
        """Print a table.
        :param rows: The table rows.
        :param name: The table name.
        :type rows: List[List[str]]
        """
        self.print()

        if name is not None:
            if style is None:
                style = f"bold {Colors.CYAN}"

            rule_char: str = "─"
            title: str = f"{rule_char} [{style}]{name}[/{style}]"
            self.console.rule(title, align="left", style="", characters=rule_char)

        self.table([{**header} for header in TABLE_HEADERS], rows, show_header=False, box=None)

    def info_table_rows_base(self) -> List[List[str]]:
        """Return the basic rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        name: str = string.stylize(self.database.name, Colors.PURPLE)
        version: str = string.stylize(f"{self.database.version.major}.{self.database.version.minor}", Colors.CYAN)

        return [
            ["Name", name],
            ["Version", version],
            ["Edition", self.database.edition.capitalize()],
            ["Hosting", self.database.platform.display],
        ]

    def info_table_rows_database(self) -> List[List[str]]:
        """Return the common rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        url: str = f"{self.database.url}/web?debug=1" if self.database.url else DISPLAY_NA
        port: str = str(self.database.rpc_port) if self.database.rpc_port else DISPLAY_NA
        expiration_date: str = (
            self.database.expiration_date.strftime("%Y-%m-%d %X")
            if self.database.expiration_date is not None
            else DISPLAY_NEVER
        )
        filestore_size: int = self.database.filestore.size if self.database.filestore is not None else 0

        return [
            ["Backend URL", url],
            ["RPC Port", port],
            ["Expiration Date", expiration_date],
            ["Database UUID", self.database.uuid or DISPLAY_NA],
            ["Database Size", string.bytes_size(self.database.size)],
            ["Filestore Size", string.bytes_size(filestore_size)],
        ]

    def info_table_rows_local(self) -> List[List[str]]:
        """Return the local-specific rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        assert isinstance(self.database, LocalDatabase)
        last_used: str = (
            self.database.last_date.strftime("%Y-%m-%d %X") if self.database.last_date is not None else DISPLAY_NEVER
        )
        filestore_path: str = (
            self.database.filestore.path.as_posix()
            if self.database.filestore is not None and self.database.filestore.path is not None
            else DISPLAY_NA
        )
        venv_path: str = self.database.venv.as_posix() if self.database.venv is not None else DISPLAY_NA
        running: bool = self.database.process.is_running
        process_id: str = str(self.database.process.pid) if self.database.process.pid else DISPLAY_NA
        addons: List[str] = [DISPLAY_NA]

        if running:
            addons_match = re.search(r"--addons-path(?:=|\s)([^\s]+)", self.database.process.command)

            if addons_match is not None:
                addons = addons_match.group(1).split(",")

        return [
            ["Last Used", last_used],
            ["Filestore Path", filestore_path],
            ["Virtualenv Path", venv_path],
            ["Whitelisted", DISPLAY_TRUE if self.database.whitelisted else DISPLAY_FALSE],
            ["Running", DISPLAY_TRUE if running else DISPLAY_FALSE],
            ["Odoo-Bin PID", process_id],
            ["Addons Paths", "\n".join(addons)],
            ["Repository", self.database.repository.full_name if self.database.repository else DISPLAY_NA],
            ["Repository URL", self.database.repository.url if self.database.repository else DISPLAY_NA],
            ["Branch", self.database.branch.name if self.database.branch else DISPLAY_NA],
            ["Branch URL", self.database.branch.url if self.database.branch else DISPLAY_NA],
        ]

    def info_table_rows_saas(self) -> List[List[str]]:
        """Return the SaaS-specific rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        assert isinstance(self.database, SaasDatabase)
        return [
            ["Support URL", f"{self.database.url}/_odoo/support"],
            ["Mode", self.database.mode.capitalize()],
            ["Status", "Active" if self.database.active else "Inactive"],
            ["Repository", self.database.repository.full_name if self.database.repository else DISPLAY_NA],
            ["Repository URL", self.database.repository.url if self.database.repository else DISPLAY_NA],
            ["Branch", self.database.branch.name if self.database.branch else DISPLAY_NA],
            ["Branch URL", self.database.branch.url if self.database.branch else DISPLAY_NA],
            ["Domain Names", "\n".join(self.database.domains or [DISPLAY_NA])],
        ]
