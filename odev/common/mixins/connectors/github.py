"""Mixins for commands that need to use a connection to GitHub."""

from odev.common.connectors import GitConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class GitConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a Github connector."""

    _connector_class: type[GitConnector] = GitConnector
    _connector_attribute_name = "github"
    github: type[GitConnector]
