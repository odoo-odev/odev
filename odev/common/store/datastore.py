"""Odev datastore (SQL database) with mappings and helpers for data types."""

import pkgutil
from importlib import import_module
from pathlib import Path
from typing import cast

from odev.common.postgres import PostgresDatabase, PostgresTable
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
        self.__load_plugins_tables()

    def __load_plugins_tables(self):
        odev_path = Path(__file__).parents[2]
        plugins = [path for path in (odev_path / "plugins").glob("*/datastore") if path.is_dir()]
        modules = pkgutil.iter_modules([directory.as_posix() for directory in plugins])

        for module_info in modules:
            module_path = cast(str, module_info.module_finder.path)  # type: ignore [union-attr]
            module_path = module_path.replace(str(odev_path.parent) + "/", "").replace("/", ".")
            module = import_module(f"{module_path}.{module_info.name}")

            for attribute in dir(module):
                obj = getattr(module, attribute)

                if isinstance(obj, type) and issubclass(obj, PostgresTable) and obj is not PostgresTable:
                    obj_name = getattr(obj, "name", None)

                    if not obj_name:
                        raise ValueError(f"Table {obj} does not have a name attribute")

                    setattr(self, obj_name, obj(self))

    def __getattribute__(self, name: str) -> PostgresTable:
        return super().__getattribute__(name)
