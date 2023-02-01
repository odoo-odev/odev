"""Mixins for commands that need to use a connection to a local PostgreSQL database."""

from typing import Type

from odev.common.connectors import PostgresConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class PostgresConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a PostgreSQL connector."""

    _connector_class: Type[PostgresConnector] = PostgresConnector
    _connector_attribute_name = "psql"
    psql: Type[PostgresConnector]
