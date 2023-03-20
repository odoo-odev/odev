"""Mixins for commands that need to use a connection to a SaaS database."""

from typing import Type

from odev.common.connectors import SaasConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class SaasConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a connector to an Odoo Online (SaaS) database."""

    _connector_class: Type[SaasConnector] = SaasConnector
    _connector_attribute_name = "_saas"
    _saas: Type[SaasConnector]
