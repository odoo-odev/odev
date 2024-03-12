"""Gets help about commands."""

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)
from urllib.parse import urlparse

from odev.common import args, progress, string
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
        format=lambda value: "[{color}]:{color}_circle:[/{color}]".format(color="green" if value else "red")
        if value is not None
        else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.name,
        title="Name",
        justify=None,
        format=None,
        total=False,
    ),
    Mapped(
        value=lambda database: database.version,
        title="Version",
        justify="right",
        format=lambda value: str(value or ""),
        total=False,
    ),
    Mapped(
        value=lambda database: database.edition,
        title="Edition",
        justify=None,
        format=lambda value: (value or "").capitalize(),
        total=False,
    ),
    Mapped(
        value=lambda database: database.size,
        title="Size (SQL)",
        justify="right",
        format=lambda value: string.bytes_size(value or 0),
        total=True,
    ),
    Mapped(
        value=lambda database: database.filestore.size if database.filestore else 0,
        title="Size (FS)",
        justify="right",
        format=lambda value: string.bytes_size(value) if value else "",
        total=True,
    ),
    Mapped(
        value=lambda database: database.last_date,
        title="Last Use",
        justify=None,
        format=lambda value: value.strftime("%Y-%m-%d %X") if value else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.whitelisted,
        title="Whitelisted",
        justify="center",
        format=lambda value: f"[bold {Colors.GREEN}]✔[bold {Colors.GREEN}]"
        if value
        else f"[bold {Colors.RED}] ❌[bold {Colors.RED}]",
        total=False,
    ),
    Mapped(
        value=lambda database: database.process.pid if database.process is not None else "",
        title="PID",
        justify="right",
        format=lambda value: str(value or ""),
        total=False,
    ),
    Mapped(
        value=lambda database: database.url,
        title="URL",
        justify=None,
        format=lambda value: value and f"[link={value}/web?debug=1]{urlparse(value).netloc}[/link]" or "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.venv.as_posix() if database.venv is not None else "",
        title="Virtual Environment",
        justify=None,
        format=lambda value: str(value or ""),
        total=False,
    ),
]

ORDER_MAPPING: MutableMapping[str, str] = {
    "name": "Name",
    "version": "Version",
    "size": "Size (SQL)",
    "size_fs": "Size (FS)",
    "date": "Last Use",
}


class ListCommand(ListLocalDatabasesMixin, Command):
    """List local Odoo databases with some information about them."""

    _name = "list"
    _aliases = ["ls"]

    names_only = args.Flag(
        aliases=["-1", "--one-column", "--names-only"],
        description="List database names one per line - useful for parsing.",
    )
    expression = args.Regex(
        aliases=["-e", "--expression"],
        description="Regular expression pattern to filter listed databases.",
    )
    show_all = args.Flag(aliases=["-a", "--all"], description="Show non-Odoo databases as well.")
    order = args.String(
        aliases=["-s", "--sort"],
        choices=list(ORDER_MAPPING.keys()),
        default="name",
        description=f"""Sort databases by name, version, database size, filestore size or last use date.
        Possible values are {string.join_and(list(ORDER_MAPPING.keys()))}.
        """,
    )

    def run(self) -> None:
        with progress.spinner("Listing databases"):
            databases = self.list_databases(
                predicate=lambda database: (not self.args.expression or self.args.expression.search(database))
                and (self.args.show_all or (LocalDatabase(database).is_odoo and not database.endswith(":template")))
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
            headers.append({"name": mapped.title or "", "justify": mapped.justify or "left"})
            totals.append(0)

        for database in databases:
            row: List[Any] = []

            with LocalDatabase(database) as db:
                for index, mapped in enumerate(TABLE_MAPPING):
                    value = mapped.value(db)
                    row.append(mapped.format(value) if callable(mapped.format) else value)

                    if mapped.total:
                        totals[index] += value or 0

            rows.append(row)

        if self.args.order != "name":
            column_index = next(
                (index for index, header in enumerate(headers) if header["name"] == ORDER_MAPPING[self.args.order]), 1
            )
            rows.sort(key=lambda row: row[column_index])

        totals_formatted: List[str] = [string.bytes_size(total) if total != 0 else "" for total in totals]
        totals_formatted[1] = f"{len(databases)} databases"
        return headers, rows, totals_formatted
