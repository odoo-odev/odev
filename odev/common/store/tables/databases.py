from dataclasses import dataclass
from typing import Literal, Optional

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

    repository: Optional[str]
    """Custom repository linked to the database."""

    branch: Optional[str]
    """Branch in the custom repository with the code for the database."""

    worktree: str
    """The name of the worktree of the database."""


class DatabaseStore(PostgresTable):
    """A class for managing Odoo databases."""

    name = "databases"

    _columns = {
        "id": "SERIAL PRIMARY KEY",
        "platform": "VARCHAR NOT NULL",
        "name": "VARCHAR NOT NULL",
        "virtualenv": "VARCHAR",
        "arguments": "TEXT",
        "whitelisted": "BOOLEAN NOT NULL DEFAULT FALSE",
        "repository": "VARCHAR",
        "branch": "VARCHAR",
        "worktree": "VARCHAR",
    }
    _constraints = {"databases_unique_name_platform": "UNIQUE(name, platform)"}

    def get(self, database: Database) -> Optional[DatabaseInfo]:
        """Get the saved values of a database."""
        result = self.database.query(
            f"""
            SELECT * FROM {self.name}
            WHERE name = {database.name!r}
                AND platform = {database.platform.name!r}
            LIMIT 1
            """,
            nocache=True,
        )

        if not result:
            return None

        return DatabaseInfo(*result[0][1:])

    def set(self, database: Database, arguments: Optional[str] = None):
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
        }

        self.database.query(
            f"""
            INSERT INTO {self.name} ({", ".join(values.keys())})
            VALUES ({", ".join(values.values())})
            ON CONFLICT (name, platform) DO
                UPDATE SET {", ".join(f'{key} = {value}' for key, value in values.items())}
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
