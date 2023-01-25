"""PostgreSQL database class."""

import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from odev.common import bash
from odev.common.databases import Database
from odev.common.mixins import PostgresConnectorMixin
from odev.common.mixins.connectors import ensure_connected
from odev.common.version import OdooVersion


class PostgresDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self.psql(self.name).__exit__(*args)
        del self.connector

    @ensure_connected
    def is_odoo(self) -> bool:
        return bool(
            self.connector.query(
                """
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON (n.oid = c.relnamespace)
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

    @lru_cache
    def odoo_process(self) -> Optional[str]:
        if not self.is_odoo():
            return None

        process = bash.execute(f"ps aux | grep -E 'odoo-bin\\s+(-d|--database)(\\s+|=){self.name}\\s' || echo -n ''")

        if process is not None:
            return process.stdout.decode()

        return None

    def odoo_process_id(self) -> Optional[int]:
        process = self.odoo_process()

        if not process:
            return None

        return int(re.split(r"\s+", process)[1])

    def odoo_process_command(self) -> Optional[str]:
        process = self.odoo_process()

        if not process:
            return None

        return " ".join(re.split(r"\s+", process)[10:])

    def odoo_rpc_port(self) -> Optional[int]:
        command = self.odoo_process_command()

        if not command:
            return None

        match = re.search(r"(?:-p|--http-port)(?:\s+|=)([0-9]{1,5})", command)

        if match is None:
            return 8069

        return int(match.group(1))

    def odoo_url(self) -> Optional[str]:
        return self.is_odoo_running() and f"http://localhost:{self.odoo_rpc_port()}/web" or None

    def is_odoo_running(self) -> bool:
        if not self.is_odoo():
            return None

        return self.odoo_process_id() is not None

    @ensure_connected
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
