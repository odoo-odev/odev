"""Gets help about commands."""

import collections
from typing import (
    Any,
    List,
    MutableMapping,
    Sequence,
    Tuple,
)
from urllib.parse import urlparse

from odev.common import progress, string
from odev.common.commands import Command
from odev.common.console import Colors
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.mixins import PostgresConnectorMixin


logger = logging.getLogger(__name__)


_Mapped = collections.namedtuple("_Mapped", ["info_key", "title", "justify", "display", "format"])

# Mapping of database information to table headers.
# Format: (info_key, title, justify, display, format)
#
# - info_key: The key of the database information to display in the table (from Database.info()).
# - title: The title of the column in the table.
# - justify: The justification of the column in the table, one of "center", "left", "right".
# - display: Whether to display the column in the table.
#     Either a boolean or a callable that takes the commands arguments and returns a boolean.
# - format: A callable that takes the value of the database information and returns
#     the formatted value to display in the table.
TABLE_MAPPING: List[_Mapped] = [
    _Mapped(
        info_key="is_odoo_running",
        title=None,
        justify=None,
        display=True,
        format=lambda value: (
            value is not None and "[{style}]⚪[/{style}]".format(style=Colors.GREEN if value else Colors.RED) or ""
        ),
    ),
    _Mapped(
        info_key="name",
        title="Name",
        justify=None,
        display=True,
        format=None,
    ),
    _Mapped(
        info_key="odoo_version",
        title="Version",
        justify="right",
        display=True,
        format=lambda value: str(value or ""),
    ),
    _Mapped(
        info_key="odoo_edition",
        title="Edition",
        justify=None,
        display=True,
        format=lambda value: (value or "").capitalize(),
    ),
    _Mapped(
        info_key="size",
        title="Size (SQL)",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: string.bytes_size(value or 0),
    ),
    _Mapped(
        info_key="odoo_filestore_size",
        title="Size (FS)",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: string.bytes_size(value) if value else "",
    ),
    _Mapped(
        info_key="odoo_filestore_path",
        title="Filestore",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value and f"[link={value.as_posix()}]{value.name}/[/link]" or "",
    ),
    _Mapped(
        info_key="odoo_venv_path",
        title="Virtualenv",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value and f"[link={value.as_posix()}]{value.parent.name}/{value.name}[/link]" or "",
    ),
    _Mapped(
        info_key="last_date",
        title="Last Use",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value and value.strftime("%Y-%m-%d %X") or "",
    ),
    _Mapped(
        info_key="odoo_process_id",
        title="PID",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: value and str(value) or "",
    ),
    _Mapped(
        info_key="odoo_url",
        title="URL",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value and f"[link={value}/web?debug=1]{urlparse(value).netloc}[/link]" or "",
    ),
    _Mapped(
        info_key="whitelisted",
        title="Whitelisted",
        justify="center",
        display=lambda args: args.details,
        format=lambda value: f"[bold {Colors.GREEN}]✔[bold {Colors.GREEN}]"
        if value
        else f"[bold {Colors.RED}] ❌[bold {Colors.RED}]",
    ),
]


class ListCommand(PostgresConnectorMixin, Command):
    """List local databases and provide information about them."""

    name = "list"
    aliases = ["ls"]
    arguments = [
        {
            "dest": "names_only",
            "aliases": ["-1", "--one-column", "--names-only"],
            "action": "store_true",
            "help": "List database names one per line - useful for parsing.",
        },
        {
            "name": "expression",
            "aliases": ["-e", "--expression"],
            "action": "store_regex",
            "help": "Regular expression pattern to filter listed databases.",
        },
        {
            "name": "details",
            "aliases": ["-d", "--details"],
            "action": "store_true",
            "help": "Display more details for each database.",
        },
        {
            "name": "include_other",
            "aliases": ["-o", "--include-other"],
            "action": "store_true",
            "help": "Display non-Odoo databases as well.",
        },
    ]

    def run(self) -> None:
        with progress.spinner("Listing databases..."):
            databases = self.list_databases()

            if not databases:
                message = "No database found"

                if self.args.expression:
                    message += f" matching pattern '{self.args.expression.pattern}'"

                raise self.error(message)

            if self.args.names_only and databases:
                return self.print(*databases, sep="\n")

            data = self.get_table_data(databases)

        self.table(*data)

    def list_databases(self) -> List[str]:
        """List the names of all local databases, excluding templates
        and the default 'postgres' database.
        """
        with self.psql() as psql:
            databases = psql.query(
                """
                SELECT datname
                FROM pg_database
                WHERE datistemplate = false
                ORDER by datname
                """
            )

        databases = [
            database[0]
            for database in databases
            if not self.args.expression or self.args.expression.search(database[0])
        ]

        if not self.args.include_other:
            databases = [database for database in databases if self.is_odoo(database)]

        return databases

    def get_table_data(
        self, databases: Sequence[str]
    ) -> Tuple[List[MutableMapping[str, str]], List[List[Any]], List[str]]:
        """Get the table data for the list of databases."""
        headers: List[MutableMapping[str, Any]] = []
        rows: List[List[Any]] = []
        totals: List[int] = []

        for mapped in TABLE_MAPPING:
            if mapped[3] is True or (callable(mapped[3]) and mapped[3](self.args)):
                headers.append({"name": mapped[1] or "", "justify": mapped[2] or "left"})
                totals.append(0)

        for database in databases:
            row: List[Any] = []
            info = self.get_database_info(database)

            for index, mapped in enumerate(TABLE_MAPPING):
                if mapped[3] is True or (callable(mapped[3]) and mapped[3](self.args)):
                    info.setdefault(mapped[0], "")
                    row.append(mapped[4](info[mapped[0]]) if callable(mapped[4]) else info[mapped[0]])

                    if mapped[0] in ("size", "odoo_filestore_size"):
                        totals[index] += info[mapped[0]] or 0

            rows.append(row)

        totals_formatted: List[str] = [string.bytes_size(total) if total != 0 else "" for total in totals]
        totals_formatted[1] = f"{len(databases)} databases"
        return headers, rows, totals_formatted

    def get_database_info(self, database: str) -> MutableMapping[str, Any]:
        """Get information about a database."""
        with LocalDatabase(database) as db:
            return db.info()

    def is_odoo(self, database: str) -> bool:
        """Check if a database is an Odoo database."""
        with LocalDatabase(database) as db:
            return db.is_odoo
