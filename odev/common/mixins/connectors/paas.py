"""Mixins for commands that need to use a connection to an Odoo SH database."""

from typing import Type

from odev.common.connectors import PaasConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class PaasConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a connector to an Odoo SH (PaaS) database."""

    _connector_class: Type[PaasConnector] = PaasConnector
    _connector_attribute_name = "_paas"
    _paas: Type[PaasConnector]
