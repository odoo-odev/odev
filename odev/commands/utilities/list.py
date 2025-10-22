"""Gets help about commands."""

from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
)

from odev.common import args, progress, string
from odev.common.commands import Command
from odev.common.console import TableHeader
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.mixins import ListLocalDatabasesMixin


logger = logging.getLogger(__name__)


@dataclass
class Mapped:
    """A mapping of database information to table headers."""

    value: Callable[[LocalDatabase], Any]
    """A lambda expression to fetch a value from a database object."""

    title: str | None
    """The title of the column in the table."""

    justify: Literal["left", "center", "right"] | None
    """The justification of the column in the table, one of "center", "left"
    or "right".
    """

    format: Callable[[Any], str] | None
    """A callable that takes the value and returns and formats it to display
    it in the table.
    """

    total: bool
    """Whether to display a total (sum of all values) at the bottom
    of the rendered table.
    """


STATUS_RUNNING = string.stylize("⬤", "color.green")
STATUS_STOPPED = string.stylize("⬤", "color.black")


TABLE_MAPPING: list[Mapped] = [
    Mapped(
        value=lambda database: database.process.is_running if database.process is not None else "",
        title=None,
        justify=None,
        format=lambda value: STATUS_RUNNING if value else STATUS_STOPPED if value is not None else "",
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
        value=lambda database: database.venv,
        title="Virtualenv",
        justify=None,
        format=lambda value: str(value) if not value._global else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.worktree,
        title="Worktree",
        justify=None,
        format=lambda value: str(value or ""),
        total=False,
    ),
    Mapped(
        value=lambda database: database.repository,
        title="Custom Repository",
        justify=None,
        format=lambda value: value.full_name if value else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.last_date,
        title="Last Used",
        justify=None,
        format=lambda value: string.ago(value) if value else "",
        total=False,
    ),
    Mapped(
        value=lambda database: database.whitelisted,
        title="Whitelisted",
        justify="center",
        format=lambda value: string.stylize("✔", "bold color.green")
        if value
        else string.stylize(" ❌", "bold color.red"),
        total=False,
    ),
]

ORDER_MAPPING: MutableMapping[str, str] = {
    "name": "Name",
    "version": "Version",
    "size": "Size (SQL)",
    "size_fs": "Size (FS)",
    "date": "Last Used",
    "venv": "Virtualenv",
    "worktree": "Worktree",
    "repository": "Custom Repository",
    "pid": "PID",
    "whitelisted": "Whitelisted",
}


class ListCommand(ListLocalDatabasesMixin, Command):
    """List local Odoo databases with their current status and information required for their management through this
    tool. This includes custom repositories, virtual environments, worktrees, sizes, last used dates, and whether they
    are whitelisted or not.

    By default, only Odoo databases are listed. Use the `--all` option to include non-Odoo databases or templates
    generated through `odev create` and `odev run` as well.

    System databases such as `postgres`, `template0`, `template1`, `odev`, and the default user database are always
    excluded from the list.
    """

    _name = "list"
    _aliases = ["ls"]

    names_only = args.Flag(
        aliases=["-1", "--names-only"],
        description="List database names one per line - useful for parsing.",
    )
    expression = args.Regex(
        aliases=["-e", "--expression"],
        description="Regular expression pattern to filter listed databases.",
    )
    show_all = args.Flag(aliases=["-a", "--all"], description="Show non-Odoo databases and templates.")
    order = args.String(
        aliases=["-s", "--sort"],
        choices=list(ORDER_MAPPING.keys()),
        default="name",
        description=f"""Sort databases by their value in one of the columns displayed.
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
                self.print("\n".join(databases), highlight=False)
                return

            data = self.get_table_data(databases)

        self.print()
        self.table(*data, box=None, title="All Databases" if self.args.show_all else "Odoo Databases")
        self.console.print(string.stylize(f"{STATUS_RUNNING} Running\n{STATUS_STOPPED} Stopped", "color.black"))
        self.console.print()

    def get_table_data(self, databases: Sequence[str]) -> tuple[list[TableHeader], list[list[Any]], list[str]]:
        """Get the table data for the list of databases."""
        headers: list[TableHeader] = []
        rows: list[list[Any]] = []
        totals: list[int] = []

        for mapped in TABLE_MAPPING:
            headers.append(TableHeader(title=mapped.title or "", align=mapped.justify or "left"))
            totals.append(0)

        for database in databases:
            row: list[Any] = []

            with LocalDatabase(database) as db:
                for index, mapped in enumerate(TABLE_MAPPING):
                    value = mapped.value(db)
                    row.append(mapped.format(value) if callable(mapped.format) else value)

                    if mapped.total:
                        totals[index] += value or 0

            rows.append(row)

        if self.args.order != "name":
            column_index = next(
                (index for index, header in enumerate(headers) if header.title == ORDER_MAPPING[self.args.order]), 1
            )
            rows.sort(key=lambda row: row[column_index])

        totals_formatted: list[str] = [string.bytes_size(total) if total != 0 else "" for total in totals]
        totals_formatted[1] = f"{len(databases)} databases"
        return headers, rows, totals_formatted
