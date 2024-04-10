"""Handling of database information."""

from abc import ABC, abstractmethod, abstractproperty
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal, Optional

from odev.common.connectors.rpc import RpcConnector
from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.version import OdooVersion


@dataclass
class Platform:
    """Information about the platform on which a database is running."""

    name: Literal["local", "remote", "saas", "paas", "dummy"]
    """The name of the platform."""

    display: str
    """The display name of the platform."""


@dataclass
class Filestore:
    """Information about the filestore of an Odoo database."""

    path: Path
    """The path to the filestore."""

    size: int
    """The size of the filestore in bytes."""


@dataclass(frozen=True)
class Branch:
    """Information about a branch of a repository."""

    name: str
    """Name of the branch."""

    repository: "Repository"
    """The repository containing the branch."""

    @property
    def url(self) -> str:
        """Return the URL of the branch."""
        return f"{self.repository.url}/tree/{self.name}"


@dataclass(frozen=True)
class Repository:
    """Information about the repository of an Odoo database."""

    name: str
    """Name of the repository."""

    organization: str
    """Name of the organization owning the repository."""

    @property
    def full_name(self) -> str:
        """Return the full name of the repository."""
        return f"{self.organization}/{self.name}"

    @property
    def url(self) -> str:
        """Return the URL of the repository."""
        return f"https://github.com/{self.full_name}"


class Database(OdevFrameworkMixin, ABC):
    """Base abstract class for manipulating databases."""

    _name: str
    """The name of the database."""

    _platform: ClassVar[Literal["local", "remote", "saas", "paas", "dummy"]]
    """The platform on which the database is running."""

    _platform_display: ClassVar[str]
    """The display name of the platform on which the database is running."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    _branch: Optional[Branch] = None
    """The branch of the repository containing custom code for the database."""

    def __init__(self, name: str, *args, **kwargs):
        """Initialize the database."""
        super().__init__(*args, **kwargs)
        self._name = name

        if self._platform is None:
            raise NotImplementedError(f"Missing `_platform` attribute in class {self.__class__.name}")

        self.rpc = RpcConnector(self)
        """The RPC proxy to the database."""

    def __repr__(self):
        """Return the representation of the database."""
        return f"{self.__class__.__name__}({self.name!r})"

    def __str__(self):
        """Return the string representation of the database."""
        return self.name

    @abstractmethod
    def __enter__(self):
        """Setup connection to the required underlying systems."""
        raise NotImplementedError

    @abstractmethod
    def __exit__(self):
        """Close connection with the required underlying systems."""
        raise NotImplementedError

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
        raise NotImplementedError

    @abstractproperty
    def version(self) -> Optional[OdooVersion]:
        """Return the Odoo version of the database."""
        raise NotImplementedError

    @abstractproperty
    def edition(self) -> Optional[Literal["community", "enterprise"]]:
        """Return the Odoo edition of the database."""
        raise NotImplementedError

    @abstractproperty
    def filestore(self) -> Filestore:
        """Return information about the Odoo filestore."""
        raise NotImplementedError

    @abstractproperty
    def size(self) -> int:
        """Return the size of the database in bytes."""
        raise NotImplementedError

    @abstractproperty
    def expiration_date(self) -> Optional[datetime]:
        """Return the expiration date of the database."""
        raise NotImplementedError

    @abstractproperty
    def uuid(self) -> Optional[str]:
        """Return the UUID of the database."""
        raise NotImplementedError

    @abstractproperty
    def last_access_date(self) -> Optional[datetime]:
        """Return the date of the last access to the database."""

    @abstractproperty
    def url(self) -> Optional[str]:
        """Return the URL to access the database."""
        raise NotImplementedError

    @abstractproperty
    def exists(self) -> bool:
        """Return whether the database exists."""
        raise NotImplementedError

    @abstractproperty
    def running(self) -> bool:
        """Return whether the database is currently running and accessible."""
        raise NotImplementedError

    @abstractproperty
    def rpc_port(self) -> Optional[int]:
        """Return the port used by the Odoo RPC interface."""
        raise NotImplementedError

    @abstractproperty
    def repository(self) -> Optional[Repository]:
        """The repository containing custom code for the database."""
        raise NotImplementedError

    @abstractproperty
    def branch(self) -> Optional[Branch]:
        """Return information about the branch of the repository containing custom
        code for the database.
        """
        raise NotImplementedError

    @property
    def models(self) -> RpcConnector:
        """Accessor for the models in the database, interfaced through the odoolib proxy.
        >>> self.models["res.partner"].search_count([])
        """
        return self.rpc

    def create(self):
        """Create the database."""
        raise NotImplementedError(f"Database creation not implemented for {self.platform.display} databases")

    def drop(self):
        """Drop the database."""
        raise NotImplementedError(f"Database deletion not implemented for {self.platform.display} databases")

    def neutralize(self):
        """Neutralize the database and make it suitable for development."""
        raise NotImplementedError(f"Database neutralization not implemented for {self.platform.display} databases")

    def dump(self, filestore: bool = False, path: Optional[Path] = None) -> Optional[Path]:
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

    def _get_dump_filename(
        self,
        filestore: bool = False,
        suffix: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> str:
        """Return the filename of the dump file.
        :param filestore: Whether to include the filestore in the dump.
        :param suffix: An optional suffix to add to the filename.
        :param extension: Force the extension for the filename, by default inferred
            from whether the filestore is present.
        """
        prefix = datetime.utcnow().strftime("%Y%m%d")
        suffix = f".{suffix}" if suffix else ""
        extension = extension if extension is not None else "zip" if filestore else "sql"
        return f"{prefix}-{self.name}.dump{suffix}.{extension}"


class DummyDatabase(Database):
    """Dummy database class used when no database is specified in commands."""

    _platform = "dummy"

    def __init__(self, name: str = "$dummy$", *args, **kwargs):
        """Initialize the dummy database."""
        super().__init__(name, *args, **kwargs)

    @property
    def platform(self) -> Platform:
        """The platform on which the database is running."""
        return Platform("dummy", "Dummy")

    @property
    def is_odoo(self) -> bool:
        """Return whether the database is an Odoo database."""
        return False

    @property
    def version(self) -> Optional[OdooVersion]:
        """Return the Odoo version of the database."""
        return None

    @property
    def edition(self) -> Optional[Literal["community", "enterprise"]]:
        """Return the Odoo edition of the database."""
        return None

    @property
    def filestore(self) -> Filestore:
        """Return information about the Odoo filestore."""
        raise NotImplementedError

    @property
    def size(self) -> int:
        """Return the size of the database in bytes."""
        return 0

    @property
    def expiration_date(self) -> Optional[datetime]:
        """Return the expiration date of the database."""
        return None

    @property
    def uuid(self) -> Optional[str]:
        """Return the UUID of the database."""
        return None

    @property
    def last_access_date(self) -> Optional[datetime]:
        """Return the date of the last access to the database."""
        return None

    @property
    def url(self) -> Optional[str]:
        """Return the URL to access the database."""
        return None

    @property
    def exists(self) -> bool:
        """Return whether the database exists."""
        return False

    @property
    def running(self) -> bool:
        """Return whether the database is currently running and accessible."""
        return False

    @property
    def rpc_port(self) -> Optional[int]:
        """Return the port used by the Odoo RPC interface."""
        return None

    @property
    def repository(self) -> Optional[Repository]:
        """The repository containing custom code for the database."""
        return None

    @property
    def branch(self) -> Optional[Branch]:
        """Return information about the branch of the repository containing custom
        code for the database.
        """
        return None

    def __enter__(self):
        return self

    def __exit__(self):
        pass
