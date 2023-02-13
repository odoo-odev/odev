from dataclasses import dataclass
from typing import Optional

from odev.common.databases import LocalDatabase
from odev.common.postgres import PostgresTable


@dataclass
class DatabaseInfo:
    """A class for storing information about a database."""

    name: str
    """The name of the database."""

    virtualenv: str
    """The path to the virtualenv of the database."""

    arguments: str
    """The arguments used to create the database."""

    whitelisted: bool
    """Whether the database is whitelisted and should not be removed automatically."""


class DatabaseStore(PostgresTable):
    """A class for managing Odoo databases."""

    name = "databases"
    _columns = {
        "id": "SERIAL PRIMARY KEY",
        "name": "VARCHAR NOT NULL",
        "virtualenv": "VARCHAR",
        "arguments": "TEXT",
        "whitelisted": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    _constraints = {"databases_unique_name": "UNIQUE(name)"}

    def set(self, database: LocalDatabase, arguments: str = None):
        """Save values for a database."""
        values = {
            "name": f"{database.name!r}",
            "virtualenv": f"{database.process.venv.path.as_posix()!r}",
            "arguments": f"{arguments!r}" if arguments else "NULL",
            "whitelisted": str(database._whitelisted),
        }

        self.database.query(
            f"""
            INSERT INTO {self.name} ({", ".join(values.keys())})
            VALUES ({", ".join(values.values())})
            ON CONFLICT (name) DO
                UPDATE SET {", ".join(f'{key} = {value}' for key, value in values.items())}
            """
        )

    def get(self, database: LocalDatabase) -> Optional[DatabaseInfo]:
        """Get the saved values of a database."""
        result = self.database.query(
            f"""
            SELECT * FROM {self.name}
            WHERE name = {database.name!r}
            LIMIT 1
            """
        )

        if not result:
            return None

        return DatabaseInfo(*result[0][1:])

    def delete(self, database: LocalDatabase):
        """Delete the saved values of a database."""
        self.database.query(
            f"""
            DELETE FROM {self.name}
            WHERE name = {database.name!r}
            """
        )
