"""Mixins for commands that need to use a connector."""

from pathlib import Path
from typing import Callable, List, Type

from odev.common.connectors import Connector, PostgresConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


def ensure_connected(func: Callable) -> Callable:
    """Decorator that ensures that the connector is connected before running the decorated method."""

    def wrapped(self, *args, **kwargs):
        if not self.connector:
            return logger.error("Connector is not initialized, use the `with` statement or call `connect` first")
        return func(self, *args, **kwargs)

    return wrapped


class ConnectorMixin:
    """Base mixin for commands that need to use a connector."""

    _connector_class: Type[Connector] = Connector
    """The class of the connector to use."""

    _connector_attribute_name: str = "connector"
    """The name of the attribute to set on the command instance.
    The attribute is added dynamically to the command instance and hence is not known to the IDE during development.
    To remediate this, the type definition for the attribute is added to the adjacent connectors.pyi file.
    Code completion and type hinting will become available after the mixin has been used and odev has been run once.
    """

    connector: Connector = None
    """The connector instance used."""

    def __init__(self, *args, **kwargs):
        """Initialize the mixin and dynamically add the connector attribute to the command instance."""
        super().__init__(*args, **kwargs)

        for mixin_cls in self.__filter_connector_mixins():
            mixin_cls.__add_connector_attribute_type_definition()
        setattr(self, self._connector_attribute_name, self._connector_class)

    def __filter_connector_mixins(self) -> List[Type["ConnectorMixin"]]:
        """Filters the ConnectorMixin class from the bases of the command class."""
        return [base for base in self.__class__.__bases__ if issubclass(base, ConnectorMixin)]

    @classmethod
    def __connector_attribute_type_definition(cls) -> str:
        """Defines how dynamic attributes should be defined in the adjacent connectors.pyi file.

        :return: The type definition for the connector attribute.
        :rtype: str
        """
        return (
            f"\n\nclass {cls.__name__}:\n"
            f'    """{cls.__doc__}\n'
            f"    Provides a `{cls._connector_class.__name__}` connector in `self.{cls._connector_attribute_name}`.\n\n"
            f"    >>> with self.{cls._connector_attribute_name}(...) as {cls._connector_attribute_name}:\n"
            f"    >>>     ...\n"
            f'    """\n\n'
            f"    {cls._connector_attribute_name}: Type[{cls._connector_class.__name__}]  # noqa: F405\n"
        )

    @classmethod
    def __add_connector_attribute_type_definition(cls):
        """This method is here to make mypy happy and provide autocompletion to IDEs."""
        pyi_file = Path(__file__).parent / "connectors.pyi"
        type_definition = cls.__connector_attribute_type_definition()

        with open(pyi_file, "r") as file:
            type_definition_exists = type_definition in file.read()

        if not type_definition_exists:
            logger.debug(
                f"{cls.__name__} has not attribute '{cls._connector_attribute_name}', "
                f"adding type definition in connectors.pyi file"
            )

            with open(pyi_file, "a+") as file:
                file.write(type_definition)


class PostgresConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a PostgreSQL connector."""

    _connector_class = PostgresConnector
    _connector_attribute_name = "psql"
