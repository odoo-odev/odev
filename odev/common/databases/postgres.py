"""PostgreSQL database class."""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from odev.common.databases import Database
from odev.common.mixins import PostgresConnectorMixin
from odev.common.mixins.connectors import ensure_connected
from odev.common.odoo import OdooBinProcess
from odev.common.version import OdooVersion


class PostgresDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    def __init__(self, name: str):
        """Initialize the database."""
        super().__init__(name)
        self.process = OdooBinProcess(self)
        """Reference to the odoo-bin process for this database."""

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self.psql(self.name).__exit__(*args)
        del self.connector

    def info(self):
        return {
            **super().info(),
            "is_odoo_running": self.process.is_running() if self.is_odoo() else None,
            "odoo_process_id": self.process.pid(),
            "odoo_process_command": self.process.command(),
            "odoo_rpc_port": self.process.rpc_port(),
            "odoo_url": self.odoo_url(),
        }

    @ensure_connected
    def is_odoo(self) -> bool:
        return bool(
            self.connector.query(
                """
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'ir_module_module'
                    AND c.relkind IN ('r', 'v', 'm')
                    AND n.nspname = current_schema
                """
            )
        )

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
        return self.is_odoo() and Path.home() / ".local/share/Odoo/filestore/" / self.name

    @lru_cache
    def odoo_filestore_size(self) -> Optional[int]:
        return self.is_odoo() and sum(f.stat().st_size for f in self.odoo_filestore_path().rglob("*") if f.is_file())

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
        with self.psql() as psql:
            result = psql.query(
                f"""
                SELECT datname
                FROM pg_database
                WHERE datname = '{self.name}'
                LIMIT 1
                """
            )
        return bool(result)

    def odoo_url(self) -> Optional[str]:
        return self.process.is_running() and f"http://localhost:{self.process.rpc_port()}/web" or None
