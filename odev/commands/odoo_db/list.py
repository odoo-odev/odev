"""Lists all the local Odoo databases in PostgreSQL."""

import re
from argparse import Namespace
from textwrap import indent

from texttable import Texttable

from odev.exceptions import InvalidArgument
from odev.structures import commands
from odev.utils import logging
from odev.utils.logging import term
from odev.utils.os import sizeof


_logger = logging.getLogger(__name__)


class ListCommand(commands.LocalDatabaseCommand):
    """
    List all Odoo databases on this computer. If a database is defined
    in PostgreSQL but not initialized with Odoo, it will not be listed here.

    A pattern can optionally be provided to filter databases based on their name.
    """

    name = "list"
    aliases = ["ls"]
    database_required = False
    arguments = [
        {
            "name": "database",
            "nargs": "?",
            "help": "Name of a database or regex pattern to filter displayed rows",
        },
        {
            "aliases": ["-r", "--running"],
            "dest": "running",
            "action": "store_true",
            "help": "Only show running databases",
        },
        {
            "aliases": ["-s", "--stopped"],
            "dest": "stopped",
            "action": "store_true",
            "help": "Only show stopped databases",
        },
        {
            "aliases": ["-f", "--fs", "--filestore"],
            "dest": "filestore",
            "action": "store_true",
            "help": "Display path the the database's filestore",
        },
        {
            "aliases": ["-S", "--size"],
            "dest": "size",
            "action": "store_true",
            "help": "Display the size of the database",
        },
        {
            "aliases": ["-l", "--last-run", "--last"],
            "dest": "last_run",
            "action": "store_true",
            "help": "Show the date and time on which the database was last run with `odev`",
        },
        {
            "aliases": ["-a", "--all"],
            "dest": "all",
            "action": "store_true",
            "help": "Display all fields",
        },
        {
            "aliases": ["-1", "--one-column"],
            "dest": "one_column",
            "action": "store_true",
            "help": "List databases one per line - useful for parsing",
        },
    ]

    def __init__(self, args: Namespace):
        if args.running and args.stopped:
            raise InvalidArgument("Arguments `running` and  `stopped` cannot be used concurrently")
        super().__init__(args)

    def _get_databases_list(self):
        try:
            self.check_database(self.args.database)
            databases = [self.args.database]
        except Exception:
            databases = self.db_list()

            if self.args.database:
                databases = filter(lambda db: re.search(self.args.database, db), databases)

        databases = set(databases)

        for database in databases.copy():
            db_is_running = self.db_runs(database)

            if (self.args.running and not db_is_running) or (self.args.stopped and db_is_running):
                databases.remove(database)

        return sorted(databases)

    def run(self):
        """
        Lists local Odoo databases.
        """

        databases = self._get_databases_list()

        if self.args.one_column:
            print("\n".join(databases))
            return 0

        if not databases:
            _logger.debug("No databases to show")
            return 0

        if len(databases) > 10 and (self.args.size or self.args.all):
            _logger.warning(f"Loading size info on {len(databases)} databases, this may take some time...")

        table_header_row = ["", "Name", "Version", "URL"]
        table_header_align = ["l" for _ in table_header_row]
        table_rows_align = ["l" for _ in table_header_row]
        table_rows = []

        if self.args.all or self.args.filestore:
            table_header_row.append("Filestore")
            table_header_align.append("l")
            table_rows_align.append("l")

        if self.args.all or self.args.size:
            table_header_row.append("Size")
            table_header_align.append("l")
            table_rows_align.append("r")

            table_header_row.append("FS Size")
            table_header_align.append("l")
            table_rows_align.append("r")

        if self.args.all or self.args.last_run:
            table_header_row.append("Last Run")
            table_header_align.append("l")
            table_rows_align.append("l")

        for database in databases:
            db_info = {
                "name": database,
                "version": self.config["databases"].get(database, "version_clean"),
                "enterprise": self.config["databases"].get(database, "enterprise"),
            }

            if not db_info["version"]:
                db_info["version"] = self.config["databases"].set(
                    database,
                    "version_clean",
                    self.db_version_clean(database),
                )[database]["version_clean"]

            if not db_info["enterprise"]:
                db_info["enterprise"] = self.config["databases"].set(
                    database,
                    "enterprise",
                    "enterprise" if self.db_enterprise(database) else "standard",
                )[database]["enterprise"]

            db_is_running = self.db_runs(database)
            table_row = [
                ("r" if db_is_running else "s") + "⬤",
                db_info["name"],
                f"""{db_info['version']} - {db_info['enterprise']}""",
                self.db_url(database) if db_is_running else "",
            ]

            if self.args.all or self.args.filestore:
                table_row.append(self.db_filestore(database))

            if self.args.all or self.args.size:
                table_row.append(sizeof(self.db_size(database)))
                table_row.append(sizeof(self.db_filestore_size(database)))

            if self.args.all or self.args.last_run:
                table_row.append(self.config["databases"].get(database, "last_run", "Never"))

            table_rows.append(table_row)

        table = Texttable()
        table.set_deco(Texttable.HEADER)
        table.set_max_width(term.width - 4)
        table.set_header_align(table_header_align)
        table.set_cols_align(table_rows_align)
        table.add_rows([table_header_row] + table_rows)

        table_text = table.draw() or ""
        table_text = re.sub(r"\n(=+)\n", term.snow4(r"\n\1\n"), table_text)
        table_text = re.sub(r"r⬤", term.green(" ⬤"), table_text)
        table_text = re.sub(r"s⬤", term.red(" ⬤"), table_text)

        print("\n" + indent(table_text, " " * 2), end="")

        return 0
