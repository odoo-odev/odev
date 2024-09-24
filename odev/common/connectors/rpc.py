"""Interact with any Odoo database using XML/JSON RPC."""

from typing import (
    TYPE_CHECKING,
    Any,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    TypedDict,
    Union,
    cast,
)
from urllib.parse import urlparse

import black
import odoolib  # type: ignore [import]

from odev.common import string
from odev.common.connectors.base import Connector
from odev.common.console import console
from odev.common.errors import ConnectorError
from odev.common.logging import LOG_LEVEL, logging
from odev.typings.odoo import Domain, RecordData, RecordDataList


if TYPE_CHECKING:
    from odev.common.databases import Database


logger = logging.getLogger(__name__)


FieldsGetMapping = Mapping[str, Mapping[str, Union[str, bool]]]
RecordMetaData = TypedDict("RecordMetaData", {"xml_id": str, "noupdate": bool})


RPC_DATA_CACHE: MutableMapping[str, MutableMapping[int, RecordData]] = {}
RPC_FIELDS_CACHE: MutableMapping[str, FieldsGetMapping] = {}
RPC_DEFAULT_CACHE: MutableMapping[str, FieldsGetMapping] = {}


class Model:
    """Extended odoolib Model class to add some convenience methods."""

    _model: odoolib.Model
    """The underlying odoolib Model instance."""

    _connector: "RpcConnector"
    """The connector to the database."""

    def __init__(self, connector: "RpcConnector", model: str):
        self._connector = connector

        if not self._connector.connected:
            self._connector.connect()

        assert self._connector._connection is not None
        self._model = self._connector._connection.get_model(model)
        RPC_DATA_CACHE.setdefault(self._name, {})
        RPC_FIELDS_CACHE.setdefault(self._name, {})
        RPC_DEFAULT_CACHE.setdefault(self._name, {})

    def __repr__(self) -> str:
        return f"{self._name}()"

    def __getattr__(self, __name: str):
        """Proxy all unknown attributes to the underlying model."""
        return self._model.__getattr__(__name)

    @property
    def _name(self) -> str:
        """Return the name of the model."""
        return cast(str, self._model.model_name)

    @property
    def env(self) -> "RpcConnector":
        """Return the connector to the database."""
        return self._connector

    @property
    def cache(self) -> MutableMapping[int, RecordData]:
        """Return the cache of records of the model."""
        return RPC_DATA_CACHE[self._name]

    @property
    def fields(self) -> FieldsGetMapping:
        """Return the fields of the model."""
        return self.fields_get()

    @property
    def fields_relational(self) -> Set[str]:
        """Relational fields as defined on the model."""
        return {name for name, field in self.fields.items() if "relation" in field}

    @property
    def fields_relational_m2o(self) -> Set[str]:
        """Many2one relational fields as defined on the model."""
        return {name for name, field in self.fields.items() if field.get("type") == "many2one"}

    @property
    def fields_relational_x2m(self) -> Set[str]:
        """X2many relational fields as defined on the model."""
        return {name for name, field in self.fields.items() if field.get("type") in ("one2many", "many2many")}

    def fields_get(self) -> FieldsGetMapping:
        """Return the fields of the model."""
        cached = RPC_FIELDS_CACHE[self._name]

        if not cached:
            cached = RPC_FIELDS_CACHE[self._name] = cast(FieldsGetMapping, self._model.fields_get())

        return cached

    def default_get(self, fields_list: Optional[list] = None) -> FieldsGetMapping:
        """Return the default value for all models fields."""
        cached = RPC_DEFAULT_CACHE[self._name]

        if not cached:
            cached = RPC_DEFAULT_CACHE[self._name] = cast(FieldsGetMapping, self._model.default_get(fields_list))

        return cached

    def read(
        self, ids: Sequence[int], fields: Optional[Sequence[str]] = None, load: Optional[str] = None
    ) -> RecordDataList:
        """Read the data of the records with the given ids.
        :param ids: The ids of the records to read
        :param fields: The fields to read, all fields by default
        :return: The data of the records with the given ids
        """
        missing_ids = []

        for id_ in ids:
            if id_ not in self.cache or not set(self.fields).issubset(set(self.cache[id_].keys())):
                missing_ids.append(id_)

        if not fields:
            fields = list(self.fields.keys())

        if missing_ids:
            missing_fields = set(fields)
        else:
            existing_fields = (
                set.intersection(*({*record.keys()} for record in self.cache.values())) if self.cache else set()
            )
            missing_fields = set(fields) - existing_fields

        if missing_ids or missing_fields:
            records = cast(RecordDataList, self._model.read(list(missing_ids or ids), list(missing_fields), load=load))

            for record in records:
                self.cache[cast(int, record["id"])] = record

        return [self.cache[id_] for id_ in ids]

    def search(
        self,
        domain: Domain,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> List[int]:
        """Search for records matching the given domain and return their ids.
        :param domain: The domain to filter the records to export
        :param offset: The offset of the first record to return
        :param limit: The maximum number of records to return
        :param order: The order in which to return the records
        :param context: Additional context to pass to the search
        :return: The ids of the records matching the given domain
        """
        return cast(List[int], self._model.search(domain, offset=offset, limit=limit, order=order, context=context))

    def search_read(
        self,
        domain: Domain,
        fields: Optional[Sequence[str]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
        load: Optional[str] = None,
    ) -> RecordDataList:
        """Search for records matching the given domain and return their data.
        :param domain: The domain to filter the records to export
        :param fields: The fields to export, all fields by default
        :param offset: The offset of the first record to return
        :param limit: The maximum number of records to return
        :param order: The order in which to return the records
        :param context: Additional context to pass to the search
        :return: The data of the records matching the given domain
        """
        ids = self.search(domain, offset=offset, limit=limit, order=order, context=context)

        if not ids:
            return []

        return self.read(ids, fields=fields, load=load)

    def read_group(
        self,
        domain: Domain,
        fields: Optional[Sequence[str]] = None,
        groupby: Optional[Union[str, Sequence[str]]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ):
        """Get the aggregated data of the records matching the given domain, grouped by the groupby clause.
        :param domain: The domain to filter the records to export
        :param fields: The fields to aggregate, all fields by default
        :param groupby: The fields to group by
        :param offset: The offset of the first record to return
        :param limit: The maximum number of records to return
        :param order: The order in which to return the records
        :param context: Additional context to pass to the search
        """
        fields = fields or []
        assert groupby is not None, "read_group() requires a groupby clause"
        return self._model.read_group(
            domain,
            fields=fields,
            groupby=groupby,
            offset=offset,
            limit=limit,
            orderby=order,
            lazy=False,
            context=context,
        )


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
        if not self.database.url:
            raise ConnectorError(
                f"URL not set for {self.database.platform.display} database {self.database.name!r}", self
            )

        return urlparse(self.database.url, scheme="https").netloc.partition(":")[0]

    @property
    def port(self) -> int:
        """Return the port to the external service."""
        if not self.database.rpc_port:
            raise ConnectorError(
                f"RPC port not set for {self.database.platform.display} database {self.database.name!r}", self
            )

        return self.database.rpc_port

    @property
    def protocol(self) -> Literal["jsonrpc", "jsonrpcs"]:
        """Return the protocol to use to reach the external service."""
        return "jsonrpcs" if self.port == 443 else "jsonrpc"

    def connect(self) -> odoolib.Connection:
        """Open a connection to the external service."""
        if not self.connected:
            if not self.database.running:
                raise ConnectorError(
                    f"Cannot establish RPC connection to {self.database.name!r}: is the database running?",
                    self,
                )

            credentials_prompt = f"{{field}} for {self.database.platform.display} database {self.database.name!r}:"
            credentials_key = self.database.name if self.database.platform.name == "local" else self.url
            credentials_platform = self.database.platform.name if self.database.platform.name == "local" else "remote"
            credentials_scope = "user"

            try:
                credentials = self.store.secrets.get(
                    credentials_key,
                    platform=credentials_platform,
                    scope=credentials_scope,
                    prompt_format=credentials_prompt,
                )
                self._connection = odoolib.get_connection(
                    hostname=self.url,
                    database=self.database.name,
                    login=credentials.login,
                    password=credentials.password,
                    protocol=self.protocol,
                    port=self.port,  # type: ignore [arg-type]
                )
                self._connection.check_login()
            except odoolib.AuthenticationError:
                logger.error(
                    f"Invalid credentials for {self.database.platform.display} "
                    f"database {self.database.name!r} ({self.database.url})"
                )
                credentials = self.store.secrets.get(
                    credentials_key,
                    platform=credentials_platform,
                    scope=credentials_scope,
                    prompt_format=credentials_prompt,
                    force_ask=True,
                )
                self._connection = None
                return self.connect()

        assert self._connection is not None, "Failed to establish RPC connection"
        self.__patch_odoolib_send()
        return self._connection

    def disconnect(self) -> None:
        """Close the connection to the external service."""
        self._connection = None
        logger.debug(f"Disconnected from {self.database.platform.display} database {self.database.name!r}'s RPC API")

    def __getitem__(self, name: str) -> Model:
        """Proxy all unknown attributes to the underlying connection, accessing a model directly."""
        if not self.connected:
            self.connect()

        return Model(self, name)

    def __patch_odoolib_send(self):
        """Monkey patch calls to `execute_kw` to log RPC calls from the connector to a database
        and catch exceptions thrown by the connector for better handling of errors.
        """
        assert self._connection is not None
        logger.debug(f"Connected to {self.database.platform.display} database {self.database.name!r}'s RPC API")
        original_send = self._connection.connector.send

        def patched_send(service_name, method, *args):
            if LOG_LEVEL == "DEBUG" and service_name == "object" and method == "execute_kw":
                arguments = [*args]
                _args = ", ".join(map(str, arguments[5]))

                def _format_key_value(key: str, value: Any) -> str:
                    return f"{key}={string.quote(value) if isinstance(value, str) else value}"

                _kwargs = ", ".join(_format_key_value(k, v) for k, v in args[6].items() if k != "context")
                _context = ", ".join(_format_key_value(k, v) for k, v in args[6].get("context") or {})

                call = f'env["{args[3]}"]'

                if _context:
                    call += f".with_context({_context})"

                call += f".{args[4]}({', '.join(filter(None, [_args, _kwargs]))})"
                call = black.format_str(call, mode=black.FileMode(line_length=120)).rstrip()
                logger.debug(f"RPC call to {self.database.platform.display} database {self.database.name!r}")
                console.code(string.indent(call, indent=4), "python")

            try:
                return original_send(service_name, method, *args)
            except odoolib.JsonRPCException as error:
                raise ConnectorError(
                    error.error.get("data", {}).get("message", "Unknown error during JSON RPC call"), self
                ) from error

        self._connection.connector.send = patched_send
