"""Gets help about commands."""

import collections
from typing import Any, List, MutableMapping, Tuple

from odev.common.commands import Command
from odev.common.databases import PostgresDatabase
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
#    the formatted value to display in the table.
TABLE_MAPPING: List[_Mapped] = [
    _Mapped(
        info_key="is_odoo",
        title=None,
        justify=None,
        display=True,
        format=lambda value: value and ":white_circle:" or "",
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
    ]

    def run(self) -> None:
        databases = self.list_databases()

        if not databases:
            message = "No database found"

            if self.args.expression:
                message += f" matching pattern '{self.args.expression.pattern}'"

            raise self.error(message)

        if self.args.names_only and databases:
            return self.print(*databases, sep="\n")

        self.table(*self.get_table_data())

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
                        AND datname != 'postgres'
                    ORDER by datname
                """
            )

        return [
            database[0]
            for database in databases
            if not self.args.expression or self.args.expression.search(database[0])
        ]

    def get_table_data(self) -> Tuple[List[MutableMapping[str, str]], List[List[Any]]]:
        """Get the table data for the list of databases."""
        databases = self.list_databases()
        headers: List[MutableMapping[str, Any]] = []
        rows: List[List[Any]] = []

        for mapped in TABLE_MAPPING:
            if mapped[3] is True or (callable(mapped[3]) and mapped[3](self.args)):
                headers.append({"name": mapped[1] or "", "justify": mapped[2] or "left"})

        for database in databases:
            row: List[Any] = []
            info = self.get_database_info(database)

            for mapped in TABLE_MAPPING:
                if mapped[3] is True or (callable(mapped[3]) and mapped[3](self.args)):
                    info.setdefault(mapped[0], "")
                    row.append(mapped[4](info[mapped[0]]) if callable(mapped[4]) else info[mapped[0]])

            rows.append(row)

        return headers, rows

    def get_database_info(self, database: str) -> MutableMapping[str, Any]:
        """Get information about a database."""
        with PostgresDatabase(database) as db:
            return db.info()
