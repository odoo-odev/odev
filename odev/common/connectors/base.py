"""Base abstract connector class to extend."""

from abc import ABC, abstractmethod
from typing import Optional


class Connector(ABC):
    """Base class for handling connection to external services."""

    _connection: Optional[object] = None
    """The instance of a connection to the service."""

    @abstractmethod
    def connect(self):
        """Connect to the external service."""
        raise NotImplementedError()

    @abstractmethod
    def disconnect(self):
        """Disconnect from the external service."""
        raise NotImplementedError()

    def __enter__(self):
        """Open a connection to the external service."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the connection to the external service."""
        self.disconnect()
