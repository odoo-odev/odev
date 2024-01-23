"""Gets help about commands."""

from argparse import Namespace
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from urllib.parse import urlparse

from odev.common import progress, string
from odev.common.commands import Command
from odev.common.console import Colors
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.mixins import ListLocalDatabasesMixin


logger = logging.getLogger(__name__)


@dataclass
class Mapped:
    """A mapping of database information to table headers."""

    value: Callable[[LocalDatabase], Any]
    """A lambda expression to fetch a value from a database object."""

    title: Optional[str]
    """The title of the column in the table."""

    justify: Optional[str]
    """The justification of the column in the table, one of "center", "left"
    or "right".
    """

    display: Union[bool, Callable[[Namespace], bool]]
    """Whether to display the column in the table.
    Either a boolean or a callable that takes the commands arguments and
    returns a boolean.
    """

    format: Optional[Callable[[Any], str]]
    """A callable that takes the value and returns and formats it to display
    it in the table.
    """

    total: bool
    """Whether to display a total (sum of all values) at the bottom
    of the rendered table.
    """


TABLE_MAPPING: List[Mapped] = [
    Mapped(
        value=lambda database: database.process.is_running if database.process is not None else "",
        title=None,
        justify=None,
        display=True,
        format=lambda value: "[{color}]:{color}_circle:[/{color}]".format(color="green" if value else "red")
        if value is not None
        else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.name,
        title="Name",
        justify=None,
        display=True,
        format=None,
        total=False,
    ),
    Mapped(
        value=lambda database: database.version,
        title="Version",
        justify="right",
        display=True,
        format=lambda value: str(value or ""),
        total=False,
    ),
    Mapped(
        value=lambda database: database.edition,
        title="Edition",
        justify=None,
        display=True,
        format=lambda value: (value or "").capitalize(),
        total=False,
    ),
    Mapped(
        value=lambda database: database.size,
        title="Size (SQL)",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: string.bytes_size(value or 0),
        total=True,
    ),
    Mapped(
        value=lambda database: database.filestore.size if database.filestore else 0,
        title="Size (FS)",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: string.bytes_size(value) if value else "",
        total=True,
    ),
    Mapped(
        value=lambda database: database.last_date,
        title="Last Use",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value.strftime("%Y-%m-%d %X") if value else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.whitelisted,
        title="Whitelisted",
        justify="center",
        display=lambda args: args.details,
        format=lambda value: f"[bold {Colors.GREEN}]✔[bold {Colors.GREEN}]"
        if value
        else f"[bold {Colors.RED}] ❌[bold {Colors.RED}]",
        total=False,
    ),
    Mapped(
        value=lambda database: database.process.pid if database.process is not None else "",
        title="PID",
        justify="right",
        display=lambda args: args.details,
        format=lambda value: str(value or ""),
        total=False,
    ),
    Mapped(
        value=lambda database: database.url,
        title="URL",
        justify=None,
        display=lambda args: args.details,
        format=lambda value: value and f"[link={value}/web?debug=1]{urlparse(value).netloc}[/link]" or "",
        total=False,
    ),
]


class ListCommand(ListLocalDatabasesMixin, Command):
    """List local databases and provide information about them."""

    name = "list"
    aliases = ["ls"]
    arguments = [
        {
            "name": "names_only",
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
        with progress.spinner("Listing databases"):
            databases = self.list_databases(
                predicate=lambda database: (not self.args.expression or self.args.expression.search(database))
                and (self.args.include_other or LocalDatabase(database).is_odoo)
            )

            if not databases:
                message = "No database found"

                if self.args.expression:
                    message += f" matching pattern '{self.args.expression.pattern}'"

                raise self.error(message)

            if self.args.names_only and databases:
                return self.print("\n".join(databases), highlight=False)

            data = self.get_table_data(databases)

        self.table(*data)

    def get_table_data(
        self, databases: Sequence[str]
    ) -> Tuple[List[MutableMapping[str, str]], List[List[Any]], List[str]]:
        """Get the table data for the list of databases."""
        headers: List[MutableMapping[str, Any]] = []
        rows: List[List[Any]] = []
        totals: List[int] = []

        for mapped in TABLE_MAPPING:
            if mapped.display is True or (callable(mapped.display) and mapped.display(self.args)):
                headers.append({"name": mapped.title or "", "justify": mapped.justify or "left"})
                totals.append(0)

        for database in databases:
            row: List[Any] = []

            with LocalDatabase(database) as db:
                for index, mapped in enumerate(TABLE_MAPPING):
                    if mapped.display is True or (callable(mapped.display) and mapped.display(self.args)):
                        value = mapped.value(db)
                        row.append(mapped.format(value) if callable(mapped.format) else value)

                        if mapped.total:
                            totals[index] += value or 0

            rows.append(row)

        totals_formatted: List[str] = [string.bytes_size(total) if total != 0 else "" for total in totals]
        totals_formatted[1] = f"{len(databases)} databases"
        return headers, rows, totals_formatted

    def get_database_info(self, database: str) -> MutableMapping[str, Any]:
        """Get information about a database."""
        with LocalDatabase(database) as db:
            return db.info()
