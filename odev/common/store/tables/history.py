from odev.common.commands import Command, DatabaseCommand
from odev.common.postgres import PostgresTable


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

    def set(self, command: Command):
        """Set the history of a command."""
        database = f"{command.database.name!r}" if isinstance(command, DatabaseCommand) else "NULL"

        self.database.query(
            f"""
            INSERT INTO {self.name} (command, database, arguments)
            VALUES ({command.name!r}, {database}, {" ".join(command.argv[1:])!r})
            ON CONFLICT (command, arguments) DO
                UPDATE SET date = CURRENT_TIMESTAMP
            """
        )

    def get(self, command: Command):
        """Get the history of a command."""
        return self.database.query(
            f"""
            SELECT * FROM {self.name}
            WHERE command = {command.name}
            ORDER BY date DESC
            """
        )
