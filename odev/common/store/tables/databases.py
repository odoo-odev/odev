from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from odev.common.databases import Database, LocalDatabase
from odev.common.postgres import PostgresTable


@dataclass
class DatabaseInfo:
    """A class for storing information about a database."""

    name: str
    """The name of the database."""

    platform: Literal["local", "remote", "saas", "paas"]
    """The platform of the database."""

    virtualenv: str
    """The path to the virtualenv of the database."""

    arguments: str
    """The arguments used to create the database."""

    whitelisted: bool
    """Whether the database is whitelisted and should not be removed automatically."""

    repository: str | None
    """Custom repository linked to the database."""

    branch: str | None
    """Branch in the custom repository with the code for the database."""

    worktree: str
    """The name of the worktree of the database."""

    url: str
    """The URL of the database."""


class DatabaseStore(PostgresTable):
    """A class for managing Odoo databases."""

    name = "databases"

    _columns: Mapping[str, str] = {
        "id": "SERIAL PRIMARY KEY",
        "platform": "VARCHAR NOT NULL",
        "name": "VARCHAR NOT NULL",
        "virtualenv": "VARCHAR",
        "arguments": "TEXT",
        "whitelisted": "BOOLEAN NOT NULL DEFAULT FALSE",
        "repository": "VARCHAR",
        "branch": "VARCHAR",
        "worktree": "VARCHAR",
        "url": "VARCHAR",
    }

    _constraints = {
        "databases_unique_name_platform": "UNIQUE(name, platform)",
        "databases_unique_name_url": "UNIQUE(name, url)",
    }

    def get(self, database: Database) -> DatabaseInfo | None:
        """Get the saved values of a database."""
        keys = ", ".join([key for key in self._columns if key != "id"])
        result = self.database.query(
            f"""
            SELECT {keys} FROM {self.name}
            WHERE name = {database.name!r}
                AND platform = {database.platform.name!r}
            LIMIT 1
            """,
            nocache=True,
        )

        if not result:
            return None

        return DatabaseInfo(*result[0])

    def set(self, database: Database, arguments: str | None = None):
        """Save values for a database."""
        values = {
            "name": f"{database.name!r}",
            "platform": f"{database.platform.name!r}",
            "virtualenv": f"{database.venv.name!r}"
            if isinstance(database, LocalDatabase) and not database.venv._global
            else "NULL",
            "arguments": f"{arguments!r}" if arguments else "NULL",
            "whitelisted": str(not isinstance(database, LocalDatabase) or database._whitelisted),
            "repository": f"{database.repository.full_name!r}" if database.repository else "NULL",
            "branch": f"{database.branch.name!r}" if database.branch is not None and database.branch.name else "NULL",
            "worktree": f"{database.worktree!r}"
            if isinstance(database, LocalDatabase) and database.worktree
            else "NULL",
            "url": f"{database.url!r}" if database.url else "NULL",
        }

        self.database.query(
            f"""
            INSERT INTO {self.name} ({", ".join(values.keys())})
            VALUES ({", ".join(values.values())})
            ON CONFLICT (name, platform) DO
                UPDATE SET {", ".join(f"{key} = {value}" for key, value in values.items())}
            """
        )

    def set_value(self, database: Database, key: str, value: str):
        """Set a value for a database."""
        self.database.query(
            f"""
            UPDATE {self.name}
            SET {key} = {value}
            WHERE name = {database.name!r}
                AND platform = {database.platform.name!r}
            """
        )

    def delete(self, database: Database):
        """Delete the saved values of a database."""
        self.database.query(
            f"""
            DELETE FROM {self.name}
            WHERE name = {database.name!r}
            """
        )
