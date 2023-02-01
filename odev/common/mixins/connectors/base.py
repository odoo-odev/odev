"""Mixins for commands that need to use a connector."""

from typing import Callable, Type

from odev.common.connectors import Connector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


def ensure_connected(func: Callable) -> Callable:
    """Decorator that ensures that the connector is connected before running the decorated method."""

    def wrapped(self, *args, **kwargs):
        if not self.connector:
            raise ConnectionError("Connector is not initialized, use the `with` statement or call `connect` first")
        return func(self, *args, **kwargs)

    return wrapped


class ConnectorMixin:
    """Base mixin for commands that need to use a connector."""

    _connector_class: Type[Connector] = Connector
    """The class of the connector to use."""

    _connector_attribute_name: str = "connector"
    """The name of the attribute to set on the command instance."""

    connector: Connector = None
    """The connector instance used."""

    def __init__(self, *args, **kwargs):
        """Initialize the mixin and dynamically add the connector attribute to the command instance."""
        super().__init__(*args, **kwargs)
        setattr(self, self._connector_attribute_name, self._connector_class)
