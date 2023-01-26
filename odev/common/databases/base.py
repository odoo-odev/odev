"""Handling of database information."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping, Optional

from odev.common.version import OdooVersion


class Database(ABC):
    """Base abstract class for manipulating databases."""

    name: str = None
    """The name of the database."""

    def __init__(self, name: str):
        """Initialize the database."""
        self.name = name

    def __repr__(self):
        """Return the representation of the database."""
        return f"{self.__class__.__name__}({self.name!r})"

    def __str__(self):
        """Return the string representation of the database."""
        return self.name

    @abstractmethod
    def __enter__(self):
        """Setup connection to the required underlying systems."""

    @abstractmethod
    def __exit__(self):
        """Close connection with the required underlying systems."""

    def info(self) -> MutableMapping[str, Any]:
        """Return information about the database."""
        return {
            "name": self.name,
            "size": self.size(),
            "exists": self.exists(),
            "is_odoo": self.is_odoo(),
            "odoo_version": self.odoo_version(),
            "odoo_edition": self.odoo_edition(),
            "odoo_filestore_path": self.odoo_filestore_path(),
            "odoo_filestore_size": self.odoo_filestore_size(),
            "last_access_date": self.last_access_date(),
        }

    @abstractmethod
    def is_odoo(self) -> bool:
        """Return whether the database is an Odoo database."""

    @abstractmethod
    def odoo_version(self) -> Optional[OdooVersion]:
        """Return the Odoo version of the database."""

    @abstractmethod
    def odoo_edition(self) -> Optional[str]:
        """Return the Odoo edition of the database."""

    @abstractmethod
    def odoo_filestore_path(self) -> Optional[Path]:
        """Return the path to the Odoo filestore on the local filesystem."""

    @abstractmethod
    def odoo_filestore_size(self) -> Optional[int]:
        """Return the size of the Odoo filestore in bytes."""

    @abstractmethod
    def size(self) -> int:
        """Return the size of the database in bytes."""

    @abstractmethod
    def last_access_date(self) -> Optional[datetime]:
        """Return the date of the last access to the database."""

    @abstractmethod
    def odoo_url(self) -> Optional[str]:
        """Return the URL to access the database."""

    @abstractmethod
    def exists(self) -> bool:
        """Return whether the database exists."""
