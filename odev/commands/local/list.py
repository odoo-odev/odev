"""Gets help about commands."""

from typing import Any, List, MutableMapping

from odev.common.commands import Command
from odev.common.databases import PostgresDatabase
from odev.common.logging import logging
from odev.common.mixins import PostgresConnectorMixin


logger = logging.getLogger(__name__)


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
            message = "No databases found"

            if self.args.expression:
                message += f" matching pattern '{self.args.expression.pattern}'"

            return logger.info(message)

        if self.args.names_only and databases:
            return self.print(*databases, sep="\n")

        self.table(self.__get_table_headers(), [self.__get_table_row(database) for database in databases])

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

    def __get_table_headers(self) -> List[MutableMapping[str, Any]]:
        """Get the table headers."""
        return [
            {"name": ""},
            {"name": "Name"},
            {"name": "Version", "justify": "right"},
            {"name": "Edition"},
        ]

    def __get_table_row(self, database: str) -> List[Any]:
        """Get information about a local database."""
        with PostgresDatabase(database) as db:
            info = db.info()

        return [
            "[green]:white_circle:[/green]" if info["is_odoo"] else "",
            info["name"],
            str(info["odoo_version"] or ""),
            (info["odoo_edition"] or "").capitalize(),
        ]
