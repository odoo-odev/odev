from dataclasses import dataclass
from datetime import datetime
from typing import List

from odev.common import string
from odev.common.commands import Command, DatabaseCommand
from odev.common.databases import Database
from odev.common.postgres import PostgresTable


@dataclass
class HistoryLine:
    """A class for storing information about command history."""

    id: int
    """The ID of the history line."""

    command: str
    """The name of the command."""

    database: str
    """The name of the database used in the command."""

    arguments: str
    """The arguments used in the command."""

    date: datetime
    """The date the command was run."""


class HistoryStore(PostgresTable):
    """A class for managing the history of commands."""

    name = "history"
    _columns = {
        "id": "SERIAL PRIMARY KEY",
        "command": "VARCHAR NOT NULL",
        "database": "VARCHAR",
        "arguments": "TEXT",
        "date": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    }
    _constraints = {"history_unique_command_arguments": "UNIQUE(command, arguments)"}

    def get(self, command: Command = None, database: Database = None) -> List[HistoryLine]:
        """Get the history of a command or a database.
        :param command: The command to get the history of.
        :param database: The database to get the history of.
        :return: The history of the command or database.
        :rtype: List[Tuple[Any]]
        """
        where_clause: str = ""
        where_clauses: List[str] = []

        if command is not None:
            where_clauses.append(f"command = {command!r}")

        if database is not None:
            where_clauses.append(f"database = {database.name!r}")

        if where_clauses:
            where_clause = f"WHERE {' AND '.join(where_clauses)}"

        result = self.database.query(
            f"""
            SELECT * FROM {self.name}
            {where_clause}
            ORDER BY date DESC
            """
        )

        return [HistoryLine(*line) for line in result]

    def set(self, command: Command):
        """Set the history of a command."""
        database = f"{command.database.name!r}" if isinstance(command, DatabaseCommand) and command.database else "NULL"
        argv = " ".join([string.quote(arg, dirty_only=True) for arg in command.argv])
        self.database.query(
            f"""
            INSERT INTO {self.name} (command, database, arguments)
            VALUES ({command.name!r}, {database}, E{argv!r})
            ON CONFLICT (command, arguments) DO
                UPDATE SET date = CURRENT_TIMESTAMP
            """
        )
