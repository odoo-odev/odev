"""Base abstract connector class to extend."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from odev.common.config import Config
    from odev.common.odev import Odev
    from odev.common.store import DataStore


class Connector(ABC):
    """Base class for handling connection to external services."""

    _connection: object | None = None
    """The instance of a connection to the service."""

    _framework: "Odev"
    """The Odev framework instance."""

    def __init__(self):
        """Initialize the connector."""
        from odev.common import framework  # noqa: PLC0415 - avoid circular import at the top level

        self._framework = framework

    def __enter__(self):
        """Open a connection to the external service."""
        self.connect()
        if self._connection is None:
            raise ConnectionError("Failed to establish connection")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the connection to the external service."""
        self.disconnect()

    def __repr__(self) -> str:
        """Return the representation of the connector."""
        return f"{self.__class__.__name__}({self.url!r})"

    @property
    @abstractmethod
    def url(self) -> str:
        """Return the URL to the external service."""
        raise NotImplementedError

    @property
    def connected(self) -> bool:
        """Return whether or not the connector is connected to the external service."""
        return self._connection is not None

    @property
    def odev(self) -> "Odev":
        """Return the Odev framework instance."""
        return self._framework

    @property
    def config(self) -> "Config":
        """Return the Odev config."""
        return self.odev.config

    @property
    def store(self) -> "DataStore":
        """Return the Odev data store."""
        return self.odev.store

    @abstractmethod
    def connect(self):
        """Connect to the external service."""

    @abstractmethod
    def disconnect(self):
        """Disconnect from the external service."""
