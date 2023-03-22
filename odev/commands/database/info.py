"""Display information about a local or remote database."""

from typing import (
    Any,
    List,
    Mapping,
    MutableMapping,
    Tuple,
)

from rich.box import HORIZONTALS
from rich.panel import Panel

from odev.common import string, style
from odev.common.commands import DatabaseCommand
from odev.common.databases import LocalDatabase, SaasDatabase
from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class InfoCommand(DatabaseCommand):
    """Fetch and display information about a database, whether local or remote
    hosted on SaaS or PaaS platforms.
    """

    name = "info"
    aliases = ["i"]

    def run(self):
        return self.print_info()

    def print_info(self):
        """Print information about the database."""
        info = self.database.info()
        table_headers, table_rows = self._info_table_data(info)
        panel_title, panel_content = self._info_panel_data(info)
        panel = Panel(
            panel_content,
            title=panel_title,
            title_align="left",
            box=HORIZONTALS,
        )

        self.print(panel)
        self.table(table_headers, table_rows, show_header=False, box=None)

    def _info_panel_data(self, info: Mapping[str, Any]) -> Tuple[str, str]:
        """Return a string representation of the database info to be displayed
        in a panel.
        :param info: The database info.
        :return: A tuple of the panel title and content.
        :rtype: Tuple[str, str]
        """
        name: str = info.get("name")
        version: OdooVersion = info.get("odoo_version")
        edition: str = info.get("odoo_edition")
        platform: str = info.get("platform")

        if platform == "saas":
            platform = "SaaS"
        elif platform == "paas":
            platform = "Odoo SH"
        else:
            platform = platform.capitalize()

        title: str = f"[bold {style.PURPLE}]{name}[/bold {style.PURPLE}]"
        content: str = string.normalize_indent(
            f"""
            {version.major}.{version.minor} - {edition.capitalize()} Edition
            [{style.BLACK}]Hosting: {platform}[/{style.BLACK}]
            """
        )

        return title, content

    def _info_table_data(self, info: Mapping[str, Any]) -> Tuple[List[MutableMapping[str, str]], List[List[str]]]:
        """Return the data to be displayed in a table.
        :param info: The database info.
        :return: A tuple of the table headers and rows.
        :rtype: Tuple[List[MutableMapping[str, str]], List[List[str]]]
        """
        rows: List[List[str]] = []
        headers: List[MutableMapping[str, Any]] = [
            {"name": "", "style": "bold", "justify": "right"},
            {"name": ""},
        ]

        rows.extend(self._info_table_rows_common(info))

        if isinstance(self.database, LocalDatabase):
            rows.extend(self._info_table_rows_local(info))

        elif isinstance(self.database, SaasDatabase):
            rows.insert(1, ["Support URL", f"{info.get('odoo_url', '')}/_odoo/support"])
            rows.extend(self._info_table_rows_saas(info))

        return headers, rows

    def _info_table_rows_common(self, info: Mapping[str, Any]) -> List[List[str]]:
        """Return the common rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        rows: List[List[str]] = []
        url: str = info.get("odoo_url", "")
        port: int = info.get("odoo_rpc_port", 0)
        expiration_date = (
            info.get("expiration_date").strftime("%Y-%m-%d %X") if info.get("expiration_date") is not None else "Never"
        )

        if url and port:
            rows.extend(
                [
                    ["Backend URL", f"{url}/web?debug=1"],
                    ["RPC Port", str(info.get("odoo_rpc_port"))],
                ]
            )

        rows.extend(
            [
                ["Expiration Date", expiration_date],
                ["Database UUID", info.get("uuid", "")],
                ["Database Size", string.bytes_size(info.get("size"))],
                ["Filestore Size", string.bytes_size(info.get("odoo_filestore_size"))],
            ]
        )

        return rows

    def _info_table_rows_local(self, info: Mapping[str, Any]) -> List[List[str]]:
        """Return the local-specific rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        filestore_path = info.get("odoo_filestore_path")
        venv_path = info.get("odoo_venv_path")

        rows: List[List[str]] = [
            ["Filestore Path", filestore_path.as_posix() if filestore_path else ""],
            ["Virtualenv Path", venv_path.as_posix() if venv_path else ""],
        ]

        if info.get("is_odoo_running"):
            self.database: LocalDatabase
            rows.extend(
                [
                    ["Odoo-Bin PID", str(info.get("odoo_process_id"))],
                    ["Addons Paths", "\n".join(path.as_posix() for path in self.database.process.addons_paths)],
                ]
            )

        return rows

    def _info_table_rows_saas(self, info: Mapping[str, Any]) -> List[List[str]]:
        """Return the SaaS-specific rows to be displayed in a table.
        :param info: The database info.
        :return: The rows.
        :rtype: List[List[str]]
        """
        return [
            ["Mode", info.get("mode").capitalize()],
            ["Status", "Active" if info.get("active", False) else "Inactive"],
            ["Domain Names", "\n".join(info.get("domains", []))],
        ]
