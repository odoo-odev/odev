"""PostgreSQL database class."""

from typing import Any, MutableMapping, Optional

from odev.common.databases import Database
from odev.common.mixins import PostgresConnectorMixin
from odev.common.mixins.connectors import ensure_connected
from odev.common.version import OdooVersion


class PostgresDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    def __enter__(self):
        """Enter the context manager."""
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        """Exit the context manager."""
        self.psql(self.name).__exit__(*args)
        del self.connector

    def info(self) -> MutableMapping[str, Any]:
        return {
            **super().info(),
            "is_odoo": self.is_odoo(),
            "odoo_version": self.odoo_version(),
            "odoo_edition": self.odoo_edition(),
        }

    @ensure_connected
    def is_odoo(self) -> bool:
        """Return whether the database is an Odoo database."""
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
        """Return the Odoo version of the database."""
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
        """Return the Odoo edition of the database."""
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
