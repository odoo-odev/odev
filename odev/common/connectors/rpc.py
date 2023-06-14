"""Interact with any Odoo database using XML/JSON RPC."""

from typing import TYPE_CHECKING, Literal, Optional
from urllib.parse import urlparse

import odoolib  # type: ignore [import]

from odev.common.connectors.base import Connector
from odev.common.logging import logging


if TYPE_CHECKING:
    from odev.common.databases import Database


logger = logging.getLogger(__name__)


class RpcConnector(Connector):
    """Interact with any Odoo database using XML/JSON RPC."""

    _connection: Optional[odoolib.Connection] = None
    """The instance of a connection to the service."""

    def __init__(self, database: "Database"):
        """Initialize the connector."""
        super().__init__()
        self.database = database
        """The database instance to connect to."""

    def __repr__(self) -> str:
        """Return the representation of the connector."""
        return f"{self.__class__.__name__}({self.database!s})"

    @property
    def url(self) -> str:
        """Return the URL to the external service."""
        return urlparse(self.database.url, scheme="https").netloc.partition(":")[0]

    @property
    def credentials_key(self) -> str:
        """Return the key to the credentials to use to reach the external service.
        Combines the database name to the URL to the external service to avoid
        conflicts between databases on different systems having the same name,
        and between local databases having the same URL.
        """
        return f"{self.database.name}:{self.url}:rpc"

    @property
    def port(self) -> int:
        """Return the port to the external service."""
        return self.database.rpc_port

    @property
    def protocol(self) -> Literal["jsonrpc", "jsonrpcs"]:
        """Return the protocol to use to reach the external service."""
        return "jsonrpcs" if self.port == 443 else "jsonrpc"

    def connect(self) -> odoolib.Connection:
        """Open a connection to the external service."""
        if not self.connected:
            try:
                credentials = self.store.secrets.get(
                    self.credentials_key,
                    prompt_format=f"{self.database.platform.display} database '{self.database.name}' {{field}}:",
                )

                self._connection = odoolib.get_connection(
                    hostname=self.url,
                    database=self.database.name,
                    login=credentials.login,
                    password=credentials.password,
                    protocol=self.protocol,
                    port=self.port,
                )
            except odoolib.AuthenticationError:
                logger.error(
                    f"Invalid credentials for {self.database.platform.display} "
                    f"database {self.database.name} ({self.database.url})"
                )
                self.store.secrets.invalidate(self.credentials_key)
                return self.connect()

        return self._connection

    def disconnect(self) -> None:
        """Close the connection to the external service."""
        self._connection = None

    def __getitem__(self, name: str) -> odoolib.Model:
        """Proxy all unknown attributes to the underlying connection, accessing a model directly."""
        if not self.connected:
            self.connect()

        return self._connection.get_model(name)
