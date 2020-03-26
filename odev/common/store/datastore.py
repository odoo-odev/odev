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
        self.databases = DatabaseStore(self)
        self.history = HistoryStore(self)
        self.secrets = SecretStore(self)
