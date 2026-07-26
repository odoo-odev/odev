"""Odev datastore (SQL database) with mappings and helpers for data types."""

from odev.common.postgres import PostgresDatabase
from odev.common.store.tables import DatabaseStore, HistoryStore, SecretStore


class DataStore(PostgresDatabase):
    """Odev datastore with mappings and helpers for specific data types."""

    databases: DatabaseStore
    """A class for managing Odoo databases."""

    history: HistoryStore
    """A class for managing the history of Odoo operations."""

    secrets: SecretStore
    """A class for managing credentials in a vault database."""

    def __init__(self, name: str = "odev"):
        super().__init__(name)

        # Every command reads the store, and it lives as long as the process does: its connection is
        # opened once here and held, rather than reopened for each of the reads a single run makes.
        # Holding it from this point also covers the tables prepared below.
        self.hold_connection()

        self.databases = DatabaseStore(self)
        self.history = HistoryStore(self)
        self.secrets = SecretStore(self)
        self.__load_tables()

    def __load_tables(self):
        for table in self.tables.values():
            if not self.table_exists(table.name):
                table.prepare_database_table()
