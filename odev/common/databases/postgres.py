"""PostgreSQL database class."""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

from odev.common.databases import Database
from odev.common.mixins import PostgresConnectorMixin, ensure_connected
from odev.common.odoo import OdooBinProcess
from odev.common.version import OdooVersion


class PostgresDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    _process: Optional[OdooBinProcess] = None
    """The Odoo process running the database."""

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self.psql(self.name).__exit__(*args)

    def info(self):
        return {
            **super().info(),
            "is_odoo_running": self.process.is_running() if self.is_odoo() else None,
            "odoo_process_id": self.process and self.process.pid(),
            "odoo_process_command": self.process and self.process.command(),
            "odoo_rpc_port": self.process and self.process.rpc_port(),
            "odoo_url": self.process and self.odoo_url(),
        }

    def is_odoo(self) -> bool:
        return self.table_exists("ir_module_module")

    @ensure_connected
    def odoo_version(self) -> Optional[OdooVersion]:
        result = self.is_odoo() and self.connector.query(
            """
            SELECT latest_version
            FROM ir_module_module
            WHERE name = 'base'
            LIMIT 1
            """
        )
        return result and OdooVersion(result[0][0]) or None

    @ensure_connected
    def odoo_edition(self) -> Optional[str]:
        if not self.is_odoo():
            return None

        result = self.connector.query(
            """
            SELECT true
            FROM ir_module_module
            WHERE license LIKE 'OEEL-%'
                AND state = 'installed'
            LIMIT 1
            """
        )
        return result and result[0][0] and "enterprise" or "community"

    def odoo_filestore_path(self) -> Optional[Path]:
        return self.is_odoo() and Path.home() / ".local/share/Odoo/filestore/" / self.name or None

    @lru_cache
    def odoo_filestore_size(self) -> Optional[int]:
        if not self.is_odoo():
            return None

        return sum(f.stat().st_size for f in self.odoo_filestore_path().rglob("*") if f.is_file())

    def odoo_url(self) -> Optional[str]:
        return self.process.is_running() and f"http://localhost:{self.process.rpc_port()}/web" or None

    def size(self) -> int:
        with self.psql() as psql:
            result = psql.query(
                f"""
                SELECT pg_database_size('{self.name}')
                LIMIT 1
                """
            )
        return result and result[0][0] or 0

    @ensure_connected
    def last_access_date(self) -> Optional[datetime]:
        result = self.is_odoo() and self.connector.query(
            """
            SELECT create_date
            FROM res_users_log
            ORDER BY create_date DESC
            LIMIT 1
            """
        )
        return result and result[0][0] or None

    def exists(self) -> bool:
        """Check if the database exists."""
        with self.psql() as psql:
            return bool(psql.database_exists(self.name))

    def create(self):
        """Create the database."""
        with self.psql() as psql:
            psql.create_database(self.name)

    def drop(self):
        """Drop the database."""
        with self.psql() as psql:
            psql.drop_database(self.name)

    @ensure_connected
    def table_exists(self, table: str) -> bool:
        """Check if a table exists in the database."""
        return self.connector.table_exists(table)

    @ensure_connected
    def create_table(self, table: str, columns: Mapping[str, str]):
        """Create a table in the database."""
        return self.connector.create_table(table, columns)

    @ensure_connected
    def query(self, query: str):
        """Execute a query on the database."""
        return self.connector.query(query)

    @property
    def process(self) -> Optional[OdooBinProcess]:
        if self._process is None:
            with self:
                if self.is_odoo():
                    self._process = OdooBinProcess(self)

        return self._process
