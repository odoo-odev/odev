"""Display information about a local or remote database."""

import re
from typing import List, cast

from odev.common import string
from odev.common.commands import DatabaseCommand
from odev.common.console import TableHeader
from odev.common.databases import LocalDatabase
from odev.common.logging import logging, silence_loggers
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


DISPLAY_NA = "N/A"
DISPLAY_NEVER = "Never"
DISPLAY_TRUE = string.stylize("✔", "color.green")
DISPLAY_FALSE = string.stylize("❌", "color.red")


class InfoCommand(DatabaseCommand):
    """Fetch and display information about a database."""

    _name = "info"
    _aliases = ["i"]

    info_headers = [
        TableHeader(style="bold", min_width=15),
        TableHeader(),
    ]

    def run(self):
        if not self._database.is_odoo:
            raise self.error(f"Database '{self._database.name}' is not an Odoo database")

        self.print_info()
        self.console.clear_line()

    def print_info(self):
        """Print information about the database."""
        self.print()
        self.table(
            self.info_headers,
            self.info_table_rows_base(),
            title=string.stylize(self._database.name.upper(), "color.purple"),
        )
        self.table(self.info_headers, self.info_table_rows_database(), title="Database")

        if isinstance(self._database, LocalDatabase):
            with silence_loggers("odev.common.connectors.git"):
                self.table(self.info_headers, self.info_table_rows_local(), title=self._database.platform.display)

    def info_table_rows_base(self) -> List[List[str]]:
        """Return the basic rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        database_version = cast(OdooVersion, self._database.version)
        database_edition = cast(str, self._database.edition).capitalize()
        name: str = string.stylize(self._database.name, "color.purple")
        version: str = string.stylize(f"{database_version.major}.{database_version.minor}", "color.cyan")

        return [
            ["Name", name],
            ["Version", version],
            ["Edition", database_edition],
            ["Hosting", self._database.platform.display],
        ]

    def info_table_rows_database(self) -> List[List[str]]:
        """Return the common rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        url: str = f"{self._database.url}/web?debug=1" if self._database.url else DISPLAY_NA
        port: str = str(self._database.rpc_port) if self._database.rpc_port else DISPLAY_NA
        expiration_date: str = (
            self._database.expiration_date.strftime("%Y-%m-%d %X")
            if self._database.expiration_date is not None
            else DISPLAY_NEVER
        )
        filestore_size: int = self._database.filestore.size if self._database.filestore is not None else 0

        return [
            ["Backend URL", url],
            ["RPC Port", port],
            ["Expiration Date", expiration_date],
            ["Database UUID", self._database.uuid or DISPLAY_NA],
            ["Database Size", string.bytes_size(self._database.size)],
            ["Filestore Size", string.bytes_size(filestore_size)],
        ]

    def info_table_rows_local(self) -> List[List[str]]:
        """Return the local-specific rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        assert isinstance(self._database, LocalDatabase)
        last_used: str = (
            self._database.last_date.strftime("%Y-%m-%d %X") if self._database.last_date is not None else DISPLAY_NEVER
        )
        filestore_path: str = (
            self._database.filestore.path.as_posix()
            if self._database.filestore is not None and self._database.filestore.path is not None
            else DISPLAY_NA
        )
        venv: str = (
            f"{self._database.venv} ({self._database.venv.path})" if not self._database.venv._global else DISPLAY_NA
        )
        addons: List[str] = [DISPLAY_NA]

        if self._database.process is None:
            running = False
            process_id = DISPLAY_NA
            worktree = DISPLAY_NA
        else:
            running = self._database.process.is_running
            process_id = str(self._database.process.pid)
            worktree = f"{self._database.worktree} ({self._database.process.odoo_path.parent})"

            if running:
                addons_match = re.search(r"--addons-path(?:=|\s)([^\s]+)", cast(str, self._database.process.command))

                if addons_match is not None:
                    addons = addons_match.group(1).split(",")

        return [
            ["Last Used", last_used],
            ["Filestore Path", filestore_path],
            ["Virtualenv", venv],
            ["Worktree", worktree],
            ["Whitelisted", DISPLAY_TRUE if self._database.whitelisted else DISPLAY_FALSE],
            ["Running", DISPLAY_TRUE if running else DISPLAY_FALSE],
            ["Odoo-Bin PID", process_id],
            ["Addons Paths", "\n".join(addons)],
            ["Repository", self._database.repository.full_name if self._database.repository else DISPLAY_NA],
            ["Repository URL", self._database.repository.url if self._database.repository else DISPLAY_NA],
            ["Branch", self._database.branch.name if self._database.branch else DISPLAY_NA],
            ["Branch URL", self._database.branch.url if self._database.branch else DISPLAY_NA],
        ]
