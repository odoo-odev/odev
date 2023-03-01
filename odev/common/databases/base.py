"""Handling of database information."""

from abc import ABC, abstractmethod, abstractproperty
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping, Optional

from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.version import OdooVersion


class Database(OdevFrameworkMixin, ABC):
    """Base abstract class for manipulating databases."""

    name: str = None
    """The name of the database."""

    _platform: str = None
    """The platform on which the database is running."""

    def __init__(self, name: str, *args, **kwargs):
        """Initialize the database."""
        super().__init__(*args, **kwargs)
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
            "platform": self.platform,
            "size": self.size,
            "exists": self.exists,
            "is_odoo": self.is_odoo,
            "odoo_version": self.odoo_version,
            "odoo_edition": self.odoo_edition,
            "odoo_filestore_path": self.odoo_filestore_path,
            "odoo_filestore_size": self.odoo_filestore_size,
            "odoo_rpc_port": self.odoo_rpc_port,
            "odoo_url": self.odoo_url,
            "last_access_date": self.last_access_date,
        }

    @property
    def platform(self) -> str:
        """The platform on which the database is running."""
        return self._platform

    @abstractproperty
    def is_odoo(self) -> bool:
        """Return whether the database is an Odoo database."""

    @abstractproperty
    def odoo_version(self) -> Optional[OdooVersion]:
        """Return the Odoo version of the database."""

    @abstractproperty
    def odoo_edition(self) -> Optional[str]:
        """Return the Odoo edition of the database."""

    @abstractproperty
    def odoo_filestore_path(self) -> Optional[Path]:
        """Return the path to the Odoo filestore on the local filesystem."""

    @abstractproperty
    def odoo_filestore_size(self) -> Optional[int]:
        """Return the size of the Odoo filestore in bytes."""

    @abstractproperty
    def size(self) -> int:
        """Return the size of the database in bytes."""

    @abstractproperty
    def last_access_date(self) -> Optional[datetime]:
        """Return the date of the last access to the database."""

    @abstractproperty
    def odoo_url(self) -> Optional[str]:
        """Return the URL to access the database."""

    @abstractproperty
    def exists(self) -> bool:
        """Return whether the database exists."""

    @abstractproperty
    def odoo_rpc_port(self) -> Optional[int]:
        """Return the port used by the Odoo RPC interface."""

    def create(self):
        """Create the database."""
        raise NotImplementedError(f"Database creation not implemented for instances of {self.__class__.name}.")

    def drop(self):
        """Drop the database."""
        raise NotImplementedError(f"Database deletion not implemented for instances of {self.__class__.name}.")

    def neutralize(self):
        """Neutralize the database and make it suitable for development."""
        raise NotImplementedError(f"Database neutralization not implemented for instances of {self.__class__.name}.")

    def dump(self, filestore: bool = False, path: Path = None) -> Optional[Path]:
        """Generate a dump file for the database.
        :param filestore: Whether to include the filestore in the dump.
        :param path: The path to the dump file.
        :return: The path to the dump file.
        :rtype: Path
        """
        raise NotImplementedError(f"Database dump not implemented for instances of {self.__class__.name}.")

    def _get_dump_filename(self, filestore: bool = False, suffix: str = None) -> str:
        """Return the filename of the dump file.
        :param filestore: Whether to include the filestore in the dump.
        :param suffix: An optional suffix to add to the filename.
        """
        prefix = datetime.now().strftime("%Y%m%d")
        suffix = f".{suffix}" if suffix else ""
        extension = "zip" if filestore else "sql"
        return f"{prefix}-{self.name}.dump{suffix}.{extension}"
