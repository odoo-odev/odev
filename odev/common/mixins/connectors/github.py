"""Mixins for commands that need to use a connection to GitHub."""

from typing import Type

from odev.common.connectors import GithubConnector
from odev.common.mixins.connectors.base import ConnectorMixin


class GithubConnectorMixin(ConnectorMixin):
    """Mixin for commands that need to use a Github connector."""

    _connector_class: Type[GithubConnector] = GithubConnector
    _connector_attribute_name = "github"
    github: Type[GithubConnector]
