"""PostgreSQL database class."""

from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional

from odev.common.connectors import PostgresConnector
from odev.common.databases import Database
from odev.common.mixins import PostgresConnectorMixin, ensure_connected
from odev.common.odoo import OdooBinProcess
from odev.common.version import OdooVersion


class LocalDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    _process: Optional[OdooBinProcess] = None
    """The Odoo process running the database."""

    connector: PostgresConnector

    _whitelisted: bool = False
    """Whether the database is whitelisted and should not be removed automatically."""

    def __init__(self, name: str):
        super().__init__(name)

        if self.is_odoo:
            info = self.store.databases.get(self)
            self._whitelisted: bool = info is not None and info.whitelisted
            self.store.databases.set(self)

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self.psql(self.name).__exit__(*args)

    def info(self):
        return {
            **super().info(),
            "is_odoo_running": self.process.is_running if self.process.is_running or self.is_odoo else None,
            "odoo_process_id": self.process and self.process.pid,
            "odoo_process_command": self.process and self.process.command,
            "odoo_rpc_port": self.process and self.process.rpc_port,
            "odoo_url": self.process and self.odoo_url,
            "last_date": self.last_date,
            "whitelisted": self.whitelisted,
            "odoo_venv_path": self.odoo_venv,
        }

    @property
    def is_odoo(self) -> bool:
        if not self.exists:
            return False

        with self:
            return self.table_exists("ir_module_module")

    @property
    def odoo_venv(self) -> Optional[Path]:
        if not self.is_odoo:
            return None

        info = self.store.databases.get(self)

        if info is None:
            return None

        return Path(info.virtualenv)

    @property
    def odoo_version(self) -> Optional[OdooVersion]:
        with self:
            result = self.is_odoo and self.connector.query(
                """
                SELECT latest_version
                FROM ir_module_module
                WHERE name = 'base'
                LIMIT 1
                """
            )

        return result and result[0][0] and OdooVersion(result[0][0]) or None

    @property
    def odoo_edition(self) -> Optional[str]:
        if not self.is_odoo:
            return None

        with self:
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

    @property
    def odoo_filestore_path(self) -> Optional[Path]:
        return self.is_odoo and self._odoo_filestore_path() or None

    def _odoo_filestore_path(self) -> Path:
        """Return the path to the filestore of the database without checking if linked to an Odoo database."""
        return Path.home() / ".local/share/Odoo/filestore/" / self.name

    @property
    def odoo_filestore_size(self) -> Optional[int]:
        if not self.is_odoo:
            return None

        return sum(f.stat().st_size for f in self.odoo_filestore_path.rglob("*") if f.is_file())

    @property
    def odoo_url(self) -> Optional[str]:
        return self.process.is_running and f"http://localhost:{self.process.rpc_port}/web" or None

    @property
    def size(self) -> int:
        with self.psql() as psql:
            result = psql.query(
                f"""
                SELECT pg_database_size('{self.name}')
                LIMIT 1
                """
            )
        return result and result[0][0] or 0

    @property
    def last_date(self) -> Optional[datetime]:
        last_access = self.last_access_date
        last_usage = self.last_usage_date

        if last_access and last_usage:
            return max(last_access, last_usage)

        return last_access or last_usage

    @property
    def last_usage_date(self) -> Optional[datetime]:
        if not self.is_odoo:
            return None

        with self.psql("odev") as psql:
            result = psql.query(
                f"""
                SELECT date
                FROM history
                WHERE database = '{self.name}'
                ORDER BY date DESC
                LIMIT 1
                """
            )
            return result and result[0][0] or None

    @property
    def last_access_date(self) -> Optional[datetime]:
        with self:
            result = self.is_odoo and self.connector.query(
                """
                SELECT create_date
                FROM res_users_log
                ORDER BY create_date DESC
                LIMIT 1
                """
            )

        return result and result[0][0] or None

    @property
    def exists(self) -> bool:
        """Check if the database exists."""
        with self.psql() as psql:
            return bool(psql.database_exists(self.name))

    def create(self, template: str = None) -> bool:
        """Create the database.

        :param template: The name of the template to copy.
        """
        with self.psql() as psql:
            return psql.create_database(self.name, template=template)

    def drop(self) -> bool:
        """Drop the database."""
        self.connector.disconnect()
        with self.psql() as psql:
            return psql.drop_database(self.name)

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
        if self._process is None and self.exists:
            with self:
                self._process = OdooBinProcess(self)

        return self._process

    @property
    def whitelisted(self) -> bool:
        """Whether the database is whitelisted and should not be removed automatically."""
        if not self.is_odoo:
            return True

        info = self.store.databases.get(self)

        if not info:
            return False

        return info.whitelisted

    @whitelisted.setter
    def whitelisted(self, value: bool):
        """Set the whitelisted status of the database."""
        self._whitelisted = value
        self.store.databases.set(self)
