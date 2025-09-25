"""Display information about a local or remote database."""

import re

from odev.common import progress, string
from odev.common.commands import DatabaseCommand
from odev.common.console import TableHeader
from odev.common.databases import LocalDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DISPLAY_NA = "N/A"
DISPLAY_NEVER = "Never"
DISPLAY_TRUE = string.stylize("✔", "color.green")
DISPLAY_FALSE = string.stylize("❌", "color.red")
EMPTY_LINE = ["", ""]


class InfoCommand(DatabaseCommand):
    """Fetch and display information about a database."""

    _name = "info"
    _aliases = ["i"]

    info_headers = [
        TableHeader(style="bold", min_width=17),
        TableHeader(),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        with progress.spinner("Gathering database information"):
            self.info = self._database.info()
            """The database information."""

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
            self.info_hosting(),
            title=string.stylize(self._database.name.upper(), "color.purple"),
        )

        self.table(self.info_headers, self.info_backend(), title="Database Information")
        self.table(self.info_headers, self.info_git(), title="Git Revisions")

        if isinstance(self._database, LocalDatabase):
            self.table(self.info_headers, self.info_local_process(), title="Local Process")

    def _stylized_info_section(self, section: str) -> dict[str, str]:
        """Return the stylized information about the database.
        :param section: The section name.
        """
        info = self.info[section].copy()
        re_parenthesis = re.compile(r"\([^\)]+\)")

        for key, value in info.items():
            if value.startswith(DISPLAY_NA) or value == DISPLAY_NEVER:
                info[key] = string.stylize(value, "color.black")
            elif value == "Yes":
                info[key] = DISPLAY_TRUE
            elif value == "No":
                info[key] = DISPLAY_FALSE

            info[key] = re_parenthesis.sub(string.stylize(r"\g<0>", "color.black"), info[key])

        return info

    def info_hosting(self) -> list[list[str]]:
        """Return the rows to be displayed in a table about the hosting of the database."""
        info = self.info["hosting"]

        return [
            ["Name", string.stylize(info["name"], "color.purple")],
            ["Version", string.stylize(info["version"], "color.cyan")],
            ["Edition", info["edition"]],
            ["Hosting", info["platform"]],
        ]

    def info_backend(self) -> list[list[str]]:
        """Return the rows to be displayed in a table about the backend of the database."""
        info = self._stylized_info_section("backend")

        return [
            ["Backend URL", info["url"]],
            ["RPC Port", info["rpc_port"]],
            ["Database UUID", info["uuid"]],
            ["Expiration Date", info["date_expire"]],
            ["Last Usage Date", info["date_usage"]] if "date_usage" in info else [],
            ["Filestore", info["filestore"]] if "filestore" in info else [],
            ["Filestore Size", info["size_filestore"]],
            ["Database Size", info["size_sql"]],
        ]

    def info_local_process(self) -> list[list[str]]:
        """Return the rows to be displayed in a table about the local process of the database."""
        info = self._stylized_info_section("backend")

        return [
            ["Running", info["running"]],
            ["Process ID", info["pid"]],
            ["Virtualenv", info["venv"]],
            ["Worktree", info["worktree"]],
            ["Addons Paths", info["addons"]],
        ]

    def info_git(self) -> list[list[str]]:
        """Return the rows to be displayed in a table about the git information of the database."""
        info = self._stylized_info_section("git")

        return [
            ["Odoo", info["odoo"]],
            ["Enterprise", info["enterprise"]],
            ["Design Themes", info["design-themes"]],
            ["Custom", info["custom"]],
        ]
