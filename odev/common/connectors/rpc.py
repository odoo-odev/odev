"""Interact with any Odoo database using XML/JSON RPC."""

import csv
import json
from io import StringIO
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypedDict,
    Union,
    cast,
)
from urllib.parse import urlparse

import black
import odoolib  # type: ignore [import]
from lxml import etree

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


class Model:
    """Extended odoolib Model class to add some convenience methods."""

    _model: odoolib.Model
    """The underlying odoolib Model instance."""

    _connector: "RpcConnector"
    """The connector to the database."""

    def __init__(self, connector: "RpcConnector", model: str):
        self._connector = connector
        self._model = self._connector._connection.get_model(model)
        RPC_DATA_CACHE.setdefault(self._name, {})
        RPC_FIELDS_CACHE.setdefault(self._name, {})

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

    def read(self, ids: Sequence[int], fields: Sequence[str] = None) -> RecordDataList:
        """Read the data of the records with the given ids.
        :param ids: The ids of the records to read
        :param fields: The fields to read, all fields by default
        :return: The data of the records with the given ids
        """
        missing_ids = set(ids) - set(self.cache.keys())

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
            records = cast(RecordDataList, self._model.read(list(missing_ids or ids), list(missing_fields), load=None))

            for record in records:
                self.cache[cast(int, record["id"])] = record

        return [self.cache[id_] for id_ in ids]

    def search(
        self, domain: Domain, offset: int = 0, limit: int = None, order: str = None, context: Mapping[str, Any] = None
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
        fields: Sequence[str] = None,
        offset: int = 0,
        limit: int = None,
        order: str = None,
        context: Mapping[str, Any] = None,
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

        return self.read(ids, fields=fields)

    def read_group(
        self,
        domain: Domain,
        fields: Sequence[str] = None,
        groupby: Union[str, Sequence[str]] = None,
        offset: int = 0,
        limit: int = None,
        order: str = None,
        context: Mapping[str, Any] = None,
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

    def __convert_defaults(
        self, ids: Sequence[int] = None, fields: Sequence[str] = None
    ) -> Tuple[Sequence[int], Sequence[str]]:
        """Default values for ids and fields to use in the `_convert_*` methods.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        :return: The Python code representation of the records with the given ids
        """
        ids = ids or list(self.cache.keys())
        fields = fields or list(self.fields.keys())
        return ids, fields

    def __convert_check_relational_complexity(self, ids: Sequence[int], fields: Sequence[str]) -> None:
        """Check the complexity of converting relational fields to XML IDs.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        """
        if len(ids) * len(set(fields) & self.fields_relational) >= 10:
            logger.warning(
                f"Converting relational fields to XML IDs is costly for the number of records and fields selected "
                f"({len(ids)} records, {len(fields)} fields), this may take a while...\n"
                f"Expected RPC calls to backend: {len(fields) * len(ids) + 1}"
            )

            if not console.confirm("Do you want to continue?", default=False):
                raise ConnectorError("Aborted conversion to XML", self._connector)

    def __convert_xml_many2one(self, node: etree._Element, value: Union[Literal[False], int]) -> None:
        """Serialize a many2one field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        if value is False:
            node.set("eval", str(value))
        else:
            field = cast(str, node.get("name"))
            record_metadata = self.env[cast(str, self.fields[field]["relation"])]._get_metadata([value])
            node.set("ref", record_metadata[value]["xml_id"])

    def __convert_xml_x2many(self, node: etree._Element, value: List[int]) -> None:
        """Serialize a x2many field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        field = cast(str, node.get("name"))
        linked_record_metadata = self.env[cast(str, self.fields[field]["relation"])]._get_metadata(value)

        def _link_command(__metadata: RecordMetaData):
            linked_record_ref = f"ref('{__metadata['xml_id']}')"
            return (
                f"Command.link({linked_record_ref})"
                if self.env.database.version.major >= 16
                else f"(4, {linked_record_ref})"
            )

        commands = ", ".join(_link_command(metadata) for metadata in linked_record_metadata.values())
        node.set("eval", f"[{commands}]")

    def __convert_xml_any(self, node: etree._Element, value: Any) -> None:
        """Serialize a field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        if value is False:
            node.set("eval", str(value))
        elif self._name == "ir.ui.view" and node.get("name") == "arch":
            parser = etree.XMLParser(remove_blank_text=True, strip_cdata=False)
            arch = etree.parse(StringIO(value), parser).getroot()

            if arch.tag == "data":
                for element in arch.iterchildren():
                    node.append(element)
            else:
                node.append(arch)
        else:
            node.text = str(value)

    def _convert_xml(self, ids: Sequence[int] = None, fields: Sequence[str] = None) -> str:
        """Serialize records with the given ids to XML.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        :return: The XML representation of the records with the given ids
        """
        ids, fields = self.__convert_defaults(ids, fields)
        self.__convert_check_relational_complexity(ids, fields)

        raw_records: RecordDataList = [record.copy() for record in self.read(ids, fields)]
        metadata = self._get_metadata(ids)
        noupdate_mapping: Dict[bool, RecordDataList] = {}

        for record in raw_records:
            record_metadata = metadata[cast(int, record["id"])]
            record_noupdate = record_metadata["noupdate"]
            record["__xml_id"] = record_metadata["xml_id"]
            noupdate_mapping.setdefault(record_noupdate, []).append(record)

        root = etree.Element("odoo")

        for noupdate, records in noupdate_mapping.items():
            if len(noupdate_mapping) > 1:
                _root = root
                root = etree.SubElement(root, "data", {"noupdate": str(int(noupdate))})
            elif noupdate:
                root.set("noupdate", str(int(noupdate)))

            for record in records:
                record_node = etree.SubElement(root, "record", {"id": record["__xml_id"], "model": self._name})

                for field, value in record.items():
                    if field in ("id", "__xml_id"):
                        continue

                    field_node = etree.SubElement(record_node, "field", {"name": field})

                    match self.fields[field]["type"]:
                        case "many2one":
                            value = cast(Union[int, Literal[False]], value)
                            self.__convert_xml_many2one(field_node, value)
                        case "one2many" | "many2many":
                            value = cast(List[int], value)
                            self.__convert_xml_x2many(field_node, value)
                        case "boolean":
                            value = cast(bool, value)
                            field_node.text = str(value)
                        case _:
                            self.__convert_xml_any(field_node, value)

            if len(noupdate_mapping) > 1:
                root = _root

        etree.indent(root, space=" " * 4)
        return etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding="utf-8",
        ).decode("utf-8")

    def _convert_json(self, ids: Sequence[int] = None, fields: Sequence[str] = None) -> str:
        """Serialize records with the given ids to JSON.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        :return: The JSON representation of the records with the given ids
        """
        ids, fields = self.__convert_defaults(ids, fields)
        return json.dumps(self.read(ids, fields), indent=4, sort_keys=True)

    def _convert_csv(self, ids: Sequence[int] = None, fields: Sequence[str] = None) -> str:
        """Serialize records with the given ids to CSV.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        :return: The CSV representation of the records with the given ids
        """
        ids, fields = self.__convert_defaults(ids, fields)
        self.__convert_check_relational_complexity(ids, fields)
        fields_m2x = set(fields) & self.fields_relational_x2m
        raw_records: RecordDataList = [record.copy() for record in self.read(ids, fields)]
        records_metadata = self._get_metadata(ids)

        for record in raw_records:
            record["id"] = records_metadata[cast(int, record["id"])]["xml_id"]

            for field in fields_m2x:
                record[field] = ", ".join(str(id_) for id_ in cast(List[int], record[field]))

        with StringIO() as output:
            fields = ["id"] + list(set(fields) - {"id"})  # ID comes first
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(raw_records)
            return output.getvalue()

    # def _export_python(self) -> str:
    #     """Serialize the current model to readable python code.
    #     :return: The python code representation of the current model
    #     """
    #     _module = ast.Module(body=[], type_ignores=[])
    #     _imports = ast.ImportFrom(
    #         module="odoo",
    #         names=[
    #             ast.alias(name="models", asname=None),
    #             ast.alias(name="fields", asname=None),
    #             ast.alias(name="api", asname=None),
    #         ],
    #         level=0,
    #     )
    #     _class = ast.ClassDef(
    #         name=self._name.title().replace(".", "").replace("_", ""),
    #         bases=[ast.Attribute(value=ast.Name(id="models", ctx=ast.Load()), attr="Model", ctx=ast.Load())],
    #         body=[
    #             ast.Assign(
    #                 lineno=0,
    #                 targets=[ast.Name(id="_name", ctx=ast.Store())],
    #                 value=ast.Str(s=self._name),
    #             ),
    #         ],
    #         keywords=[],
    #         decorator_list=[],
    #     )

    #     _fields = []
    #     _computes = []

    #     for field, field_data in self.fields.items():
    #         _field = ast.Call(
    #             func=ast.Name(id=f"fields.{field_data['type'].capitalize()}", ctx=ast.Load()),
    #             args=[],
    #             keywords=[],
    #         )

    #         append_string = re.match(field, field_data["string"].replace(" ", "_"), flags=re.IGNORECASE) is None

    #         if "relation" in field_data:
    #             _field.args.append(ast.Str(s=field_data["relation"]))

    #             if append_string:
    #                 _field.keywords.append(ast.keyword(arg="string", value=ast.Str(s=field_data["string"])))
    #         else:
    #             if append_string:
    #                 _field.args.append(ast.Str(s=field_data["string"]))

    #         if field_data.get("required"):
    #             _field.keywords.append(ast.keyword(arg="required", value=ast.NameConstant(value=True)))

    #         if field_data.get("index"):
    #             _field.keywords.append(ast.keyword(arg="index", value=ast.NameConstant(value=True)))

    #         if field_data.get("copy"):
    #             _field.keywords.append(ast.keyword(arg="copy", value=ast.NameConstant(value=True)))

    #         if field_data.get("translate"):
    #             _field.keywords.append(ast.keyword(arg="translate", value=ast.NameConstant(value=True)))

    #         if field_data.get("depends") or field_data.get("related"):
    #             if field_data.get("related"):
    #                 _field.keywords.append(
    #                     ast.keyword(arg="related", value=ast.NameConstant(value=".".join(field_data["related"])))
    #                 )
    #             else:
    #                 _field.keywords.append(ast.keyword(arg="compute", value=ast.NameConstant(value=f"_compute_{field}")))
    #                 _computes.append(
    #                     ast.FunctionDef(
    #                         name=f"_compute_{field}",
    #                         lineno=0,
    #                         args=ast.arguments(
    #                             args=[ast.arg(arg="self", annotation=None)],
    #                             posonlyargs=[],
    #                             vararg=None,
    #                             kwonlyargs=[],
    #                             kw_defaults=[],
    #                             kwarg=None,
    #                             defaults=[],
    #                         ),
    #                         body=[
    #                             ast.For(
    #                                 target=ast.Name(id="record", ctx=ast.Store()),
    #                                 iter=ast.Name(id="self", ctx=ast.Load()),
    #                                 lineno=0,
    #                                 body=[
    #                                     ast.Assign(
    #                                         lineno=0,
    #                                         targets=[ast.Name(id=f"record.{field}", ctx=ast.Store())],
    #                                         value=ast.NameConstant(value=False),
    #                                     ),
    #                                 ],
    #                                 orelse=[]
    #                             ),
    #                         ],
    #                         decorator_list=[
    #                             ast.Call(
    #                                 func=ast.Name(id="api.depends", ctx=ast.Load()),
    #                                 args=[ast.Str(s=depends) for depends in field_data["depends"]],
    #                                 keywords=[],
    #                             ),
    #                         ],
    #                         returns=None,
    #                         type_comment=None,
    #                     )
    #                 )

    #                 if field_data.get("inverse"):
    #                     _field.keywords.append(ast.keyword(arg="inverse", value=ast.NameConstant(value=f"_inverse_{field}")))
    #                     _computes.append(
    #                         ast.FunctionDef(
    #                             name=f"_inverse_{field}",
    #                             lineno=0,
    #                             args=ast.arguments(
    #                                 args=[ast.arg(arg="self", annotation=None)],
    #                                 posonlyargs=[],
    #                                 vararg=None,
    #                                 kwonlyargs=[],
    #                                 kw_defaults=[],
    #                                 kwarg=None,
    #                                 defaults=[],
    #                             ),
    #                             body=[
    #                                 ast.For(
    #                                     target=ast.Name(id="record", ctx=ast.Store()),
    #                                     iter=ast.Name(id="self", ctx=ast.Load()),
    #                                     lineno=0,
    #                                     body=[ast.Pass()],
    #                                     orelse=[]
    #                                 ),
    #                             ],
    #                             decorator_list=[],
    #                             returns=None,
    #                             type_comment=None,
    #                         )
    #                     )

    #             if field_data.get("store"):
    #                 _field.keywords.append(ast.keyword(arg="store", value=ast.NameConstant(value=True)))

    #             if not field_data.get("readonly"):
    #                 _field.keywords.append(ast.keyword(arg="readonly", value=ast.NameConstant(value=False)))
    #         else:
    #             if field_data.get("readonly"):
    #                 _field.keywords.append(ast.keyword(arg="readonly", value=ast.NameConstant(value=True)))

    #         _fields.append(
    #             ast.Assign(
    #                 lineno=0,
    #                 targets=[ast.Name(id=field, ctx=ast.Store())],
    #                 value=_field,
    #             )
    #         )

    #     _module.body.extend([_imports, _class])
    #     _class.body.extend(_fields)
    #     _class.body.extend(_computes)
    #     return black.format_str(ast.unparse(_module), mode=black.FileMode(line_length=120)).rstrip()

    def _get_metadata(self, ids: Sequence[int] = None) -> Dict[int, RecordMetaData]:
        """Get the metadata of the records with the given ids.
        :param ids: The ids of the records to get the metadata of
        :return: The metadata of the records with the given ids in a dict indexed by record id in format:
        >>> {
        >>>    "xml_id": "module.name",
        >>>    "noupdate": bool,
        >>> }
        """
        if not ids:
            return {}

        metadata = self.env["ir.model.data"].search_read(
            domain=[("model", "=", self._name), ("res_id", "in", ids)],
            fields=["res_id", "complete_name", "noupdate"],
            order="id DESC",
        )

        clean_metadata: Dict[int, RecordMetaData] = {
            cast(int, record["res_id"]): {
                "xml_id": cast(str, record["complete_name"]),
                "noupdate": cast(bool, record["noupdate"]),
            }
            for record in sorted(metadata, key=lambda record: record["id"], reverse=True)
        }

        for id_ in set(ids) - clean_metadata.keys():
            clean_metadata[id_] = {
                "xml_id": f"__unknown__.{self._name.replace('.', '_')}_{id_}",
                "noupdate": False,
            }

        return clean_metadata


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
            if not self.database.running:
                raise ConnectorError(
                    f"Cannot establish RPC connection to {self.database.name!r}: is the database running?",
                    self,
                )

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
