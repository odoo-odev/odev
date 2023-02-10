from odev.common.commands import Command, DatabaseCommand
from odev.common.databases import OdevDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class History(OdevDatabase):
    """A class for managing the history of commands."""

    _table = "history"

    _columns = {
        "id": "SERIAL PRIMARY KEY",
        "command": "VARCHAR NOT NULL",
        "database": "VARCHAR",
        "arguments": "TEXT",
        "date": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    }

    def _prepare_database(self):
        prepared = super()._prepare_database()

        with self:
            self.query(
                f"""
                DO $$
                BEGIN
                    BEGIN
                        ALTER TABLE {self._table}
                        ADD CONSTRAINT history_unique_command_arguments
                        UNIQUE(command, arguments);
                    EXCEPTION
                        WHEN duplicate_table THEN
                        WHEN duplicate_object THEN
                            NULL;
                    END;
                END $$;
                """
            )

        return prepared

    def set(self, command: Command):
        """Set the history of a command."""
        database = f"{command.database.name!r}" if isinstance(command, DatabaseCommand) else "NULL"

        with self:
            self.query(
                f"""
                INSERT INTO {self._table} (command, database, arguments)
                VALUES ({command.name!r}, {database}, {" ".join(command.argv[1:])!r})
                ON CONFLICT (command, arguments) DO
                    UPDATE SET date = CURRENT_TIMESTAMP
                """
            )

    def get(self, command: Command):
        """Get the history of a command."""
        with self:
            return self.query(
                f"""
                SELECT * FROM {self._table}
                WHERE command = {command.name}
                ORDER BY date DESC
                """
            )


history: History = History()
