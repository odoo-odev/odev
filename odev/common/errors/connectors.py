from typing import TYPE_CHECKING

from .odev import OdevError


if TYPE_CHECKING:
    from odev.common.connectors.base import Connector


class ConnectorError(OdevError):
    """Custom exception for errors raised while using a connector."""

    def __init__(self, message: str, connector: "Connector", *args, **kwargs):
        """
        Initialize the exception.

        :param message: the error message.
        :param command: the connector that raised the exception.
        """
        super().__init__(message, *args, **kwargs)
        self.connector: "Connector" = connector
