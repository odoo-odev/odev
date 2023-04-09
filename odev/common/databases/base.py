"""Handling of database information."""

from abc import ABC, abstractmethod, abstractproperty
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal, Optional

from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.version import OdooVersion


@dataclass
class Platform:
    """Information about the platform on which a database is running."""

    name: Literal["local", "saas", "paas"]
    """The name of the platform."""

    display: str
    """The display name of the platform."""


@dataclass
class Filestore:
    """Information about the filestore of an Odoo database."""

    path: Optional[Path]
    """The path to the filestore."""

    size: int
    """The size of the filestore in bytes."""


class Database(OdevFrameworkMixin, ABC):
    """Base abstract class for manipulating databases."""

    _name: str = None
    """The name of the database."""

    _platform: ClassVar[Literal["local", "saas", "paas"]] = None
    """The platform on which the database is running."""

    _platform_display: ClassVar[str] = None
    """The display name of the platform on which the database is running."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    def __init__(self, name: str, *args, **kwargs):
        """Initialize the database."""
        super().__init__(*args, **kwargs)
        self._name = name

        if self._platform is None:
            raise NotImplementedError(f"Missing `_platform` attribute in class {self.__class__.name}")

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

    @property
    def name(self) -> str:
        """The name of the database."""
        return self._name

    @property
    def platform(self) -> Platform:
        """The platform on which the database is running."""
        return Platform(self._platform, self._platform_display or self._platform.title())

    @abstractproperty
    def is_odoo(self) -> bool:
        """Return whether the database is an Odoo database."""

    @abstractproperty
    def version(self) -> Optional[OdooVersion]:
        """Return the Odoo version of the database."""

    @abstractproperty
    def edition(self) -> Optional[str]:
        """Return the Odoo edition of the database."""

    @abstractproperty
    def filestore(self) -> Filestore:
        """Return information about the Odoo filestore."""

    @abstractproperty
    def size(self) -> int:
        """Return the size of the database in bytes."""

    @abstractproperty
    def expiration_date(self) -> Optional[datetime]:
        """Return the expiration date of the database."""

    @abstractproperty
    def uuid(self) -> Optional[str]:
        """Return the UUID of the database."""

    @abstractproperty
    def last_access_date(self) -> Optional[datetime]:
        """Return the date of the last access to the database."""

    @abstractproperty
    def url(self) -> Optional[str]:
        """Return the URL to access the database."""

    @abstractproperty
    def exists(self) -> bool:
        """Return whether the database exists."""

    @abstractproperty
    def rpc_port(self) -> Optional[int]:
        """Return the port used by the Odoo RPC interface."""

    def create(self):
        """Create the database."""
        raise NotImplementedError(f"Database creation not implemented for {self.platform.display} databases")

    def drop(self):
        """Drop the database."""
        raise NotImplementedError(f"Database deletion not implemented for {self.platform.display} databases")

    def neutralize(self):
        """Neutralize the database and make it suitable for development."""
        raise NotImplementedError(f"Database neutralization not implemented for {self.platform.display} databases")

    def dump(self, filestore: bool = False, path: Path = None) -> Optional[Path]:
        """Generate a dump file for the database.
        :param filestore: Whether to include the filestore in the dump.
        :param path: The path to the dump file.
        :return: The path to the dump file.
        :rtype: Path
        """
        raise NotImplementedError(f"Database dump not implemented for {self.platform.display} databases")

    def restore(self, file: Path):
        """Restore the database from a dump file.
        :param file: The path to the dump file.
        """
        raise NotImplementedError(f"Database restore not implemented for {self.platform.display} databases")

    def _get_dump_filename(self, filestore: bool = False, suffix: str = None, extension: str = None) -> str:
        """Return the filename of the dump file.
        :param filestore: Whether to include the filestore in the dump.
        :param suffix: An optional suffix to add to the filename.
        :param extension: Force the extension for the filename, by default inferred
            from whether the filestore is present.
        """
        prefix = datetime.now().strftime("%Y%m%d")
        suffix = f".{suffix}" if suffix else ""
        extension = extension if extension is not None else "zip" if filestore else "sql"
        return f"{prefix}-{self.name}.dump{suffix}.{extension}"
