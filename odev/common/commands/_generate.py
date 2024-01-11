"""Generate code from templates."""

import random
import re
import shutil
from abc import ABC
from collections import defaultdict
from keyword import kwlist
from pathlib import Path
from typing import (
    Any,
    List,
    Mapping,
    MutableMapping,
    Sequence,
    Set,
    Tuple,
    Union,
)
from urllib.parse import urlencode, urlunparse

import imgkit
from unidecode import unidecode

from odev.common import progress, string
from odev.common._generate import CodeGeneratorConfig
from odev.common._template import Template
from odev.common.commands import DatabaseCommand
from odev.common.console import console
from odev.common.logging import logging
from odev.common.version import OdooVersion
from odev.typings.odoo import RecordData


logger = logging.getLogger(__name__)


RE_SPACE = re.compile(r"[.\s]")
RE_NON_WORD_CHARACTERS = re.compile(r"[\W]")
RE_UNDERSCORE = re.compile(r"\_+")
RE_UNDERSCORE_MULTI = re.compile(r"(?<=[\W])_+")
RE_TRAILING_UNDERSCORE = re.compile(r"\_+$")
RE_X = re.compile(r"(?<=['\W_\s])x_(studio_)?|^x_(studio_)?")
RE_ATTRIBUTE = re.compile(r"record\[['\"]?(\w*)['\"]?\]")

ICON_COLORS = [
    "oorange",
    "opink",
    "oyellow",
    "ogray",
    "oteal",
    "oblue1",
    "oblue2",
    "ored",
    "ogreen",
]

ICON_OPTIONS = {
    "transparent": "",
    "format": "png",
    "height": "70",
    "width": "70",
    "quiet": "",
}

RESERVED_FIELDS_MAPPING = {
    "x_name": "name_custom",
    "x_icon": "x_icon",
}

DEFAULT_MODULE_EXPORT = "__export_module__"
DEFAULT_MODULE_LIST = [
    DEFAULT_MODULE_EXPORT,
    "studio_customization",
]


class CodeGeneratorCommand(DatabaseCommand, ABC):
    """Export modules from a database and generate code files from templates."""

    arguments = [
        {
            "name": "path",
            "aliases": ["-P", "--path"],
            "help": "Path to the directory where the code files will be generated.",
            "action": "store_path",
            "default": Path.cwd(),
        },
        {
            "name": "name",
            "aliases": ["-n", "--name"],
            "help": "Name of the module to generate code for.",
            "default": "scaffolded_module",
        },
        {
            "name": "version",
            "aliases": ["-V", "--version"],
            "help": "The Odoo version to use for generating code.",
        },
        {
            "name": "type",
            "aliases": ["-t", "--type"],
            "choices": ["saas", "sh"],
            "help": "The type of module to generate code for.",
            "default": "sh",
        },
        {
            "name": "pretty",
            "aliases": ["--no-pretty"],
            "action": "store_false",
            "help": "Whether to pretty print the generated code or not.",
        },
        {
            "name": "pretty_python",
            "aliases": ["--no-pretty-python"],
            "action": "store_false",
            "help": "Whether to pretty print the generated Python code or not.",
        },
        {
            "name": "pretty_xml",
            "aliases": ["--no-pretty-xml"],
            "action": "store_false",
            "help": "Whether to pretty print the generated XML code or not.",
        },
        {
            "name": "pretty_import",
            "aliases": ["--no-pretty-import"],
            "action": "store_false",
            "help": "Whether to pretty print the import code or not.",
        },
        {
            "name": "autoflake",
            "aliases": ["--no-autoflake"],
            "action": "store_false",
            "help": "Whether to run autoflake on the generated code or not.",
        },
        {
            "name": "line_length",
            "aliases": ["-l", "--line-length"],
            "type": int,
            "help": "The maximum line length to use when formatting the generated code.",
            "default": 120,
        },
        {
            "name": "comment",
            "aliases": ["--comment"],
            "action": "store_true",
            "help": "Whether to add comments to the generated code or not.",
        },
        {
            "name": "modules",
            "aliases": ["-m", "--modules"],
            "action": "store_comma_split",
            "help": "Comma-separated list of modules to export.",
            "default": DEFAULT_MODULE_LIST,
        },
        {
            "name": "models",
            "aliases": ["-M", "--models"],
            "action": "store_comma_split",
            "help": "Comma-separated list of models to export.",
            "default": [],
        },
        {
            "name": "regex",
            "aliases": ["--no-regex"],
            "action": "store_false",
            "help": "Use regular expressions to match models.",
        },
    ]

    _config: CodeGeneratorConfig = None
    """The configuration for the code generator."""

    _data: MutableMapping[str, Any] = None
    """The data to generate the code with, possibly exported from a database."""

    _records: MutableMapping[str, List[RecordData]] = None
    """The records to export from a database."""

    _modules: List[str] = None
    """List of all modules to export."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._modules = self.args.modules

    def sanitize_name(self, field: str) -> str:
        """Sanitize a field or model name for Odoo.
        :param field: The field name to sanitize.
        :return: The sanitized field name.
        """
        field = field.lower()
        field = re.sub(RE_SPACE, "_", field)
        field = re.sub(RE_NON_WORD_CHARACTERS, "", field)
        field = re.sub(RE_UNDERSCORE, "_", field)
        field = re.sub(RE_TRAILING_UNDERSCORE, "", field)
        field = unidecode(field)
        return field

    def sanitize_field_python(self, field: str) -> str:
        """Sanitize a field name for Odoo in Python.
        :param field: The field name to sanitize.
        :return: The sanitized field name.
        """
        if field in RESERVED_FIELDS_MAPPING:
            return RESERVED_FIELDS_MAPPING[field]

        # Remove usage of `x_` prefixes reserved for custom fields
        # in SaaS environments:
        #   x_data -> data
        #   default_x_field_x_data -> default_field_data
        #   capex_po -> capex_po
        field = re.sub(RE_X, "", field)

        #   record['test'] -> record.test
        field = re.sub(RE_ATTRIBUTE, r"record.\1", field)

        # Replace multiple underscores by only one
        field = re.sub(RE_UNDERSCORE_MULTI, "_", field)

        if not field:
            return "x_"

        # Avoid starting numbers by adding an underscore
        if field[0].isdigit() or field in kwlist:
            field = f"_{field}"

        return field

    def sanitize_field_xml(self, field: str) -> str:
        """Sanitize a field name for Odoo in XML.
        :param field: The field name to sanitize.
        :return: The sanitized field name.
        """
        if field.startswith("x_") or field.startswith("studio_"):
            return field

        return f"x_{field}"

    def sanitize_model(self, model: str) -> str:
        """Sanitize a model name for Odoo.
        :param model: The model name to sanitize.
        """
        model = self.sanitize_name(model)
        model = model.replace("_", ".")
        model = re.sub(RE_NON_WORD_CHARACTERS, ".", model)
        model = unidecode(model)
        model = re.sub(RE_UNDERSCORE_MULTI, ".", model)
        return model.lower()

    def sanitize_server_action(self, action: str) -> str:
        """Sanitize a server action's Python code for Odoo.
        :param action: The server action to sanitize.
        """
        action = action.replace(" env", " self.env")
        action = action.replace("object.", "self.")
        action = action.replace("record.", "self.")
        action = action.replace(" model.", " self.")
        action = re.sub(r"([\s\W])?context([\W]?)", r"\1self.context\2", action)
        action = re.sub(r"object\[['\"]?(\w*)['\"]?\]", r"self.\1", action)

        if "action = " in action.replace("action = {...}", ""):
            action = ("\n" * 2) + (" " * 8) + "return action"

        return action

    def sanitize_domain(self, domain: str) -> str:
        """Sanitize the string representation of an Odoo domain.
        :param domain: The domain to sanitize.
        """
        domain = domain.replace("&", "&amp;")
        domain = domain.replace("<", "&lt;")
        domain = domain.replace(">", "&gt;")
        domain = domain.replace('"', "'")
        return domain.strip()

    def sanitize_ref(self, ref: str) -> str:
        """Sanitize a reference to an ID to use in magic numbers or Odoo commands.
        :param ref: The reference to sanitize.
        :return: The sanitized reference.
        """
        if not ref.isdigit():
            ref = f"ref('{ref}')"

        ref_format = "(4, {id})" if self.version.major < 16 else "Command.link({id})"
        return ref_format.format(id=ref)

    def convert_model_id_to_name(self, model_id: str) -> str:
        """Convert a model ID to a model name.
        :param model_id: The model ID to convert.
        :return: The model name.
        """
        return self.sanitize_model(model_id.split(".", 1)[-1].removeprefix("model_"))

    @property
    def version(self) -> OdooVersion:
        """The Odoo version to use for generating code."""
        version: Union[OdooVersion, str] = self.args.version or self.database.version or "master"

        if isinstance(version, str):
            version = OdooVersion(version)

        return version

    @property
    def config(self) -> CodeGeneratorConfig:
        """The configuration for the code generator."""
        if not self._config:
            self._config = CodeGeneratorConfig(self.version)

        return self._config

    @property
    def data(self) -> MutableMapping[str, Any]:
        """The data to generate the code with, possibly exported from a database."""
        if self._data is None:
            self._data = {key: {} for key in self.config}
            self._prefill_data()
            self._export_data()
            self._postprocess_data()

        return self._data

    @property
    def models(self) -> List[str]:
        """The models to export."""
        if self.args.models:
            models = set(self.args.models)
        else:
            models = {model for model, config in self.config["models"].items() if config.get("export", True)}

            if self.args.modules != DEFAULT_MODULE_LIST and not self.args.models:
                grouped_models = self.database.rpc["ir.model.data"].read_group(
                    [("module", "in", self.args.modules)],
                    fields=["model"],
                    groupby="model",
                )

                models |= {model["model"] for model in grouped_models}

                if self.args.type == "sh":
                    models -= {"ir.model.fields", "ir.model.constraint"}

        existing_models: Mapping[str, str] = self.database.rpc["ir.model"].search_read(
            [("model", "in", list(models))],
            fields=["model"],
        )

        return sorted(model["model"] for model in existing_models)

    @property
    def records(self) -> MutableMapping[str, List[RecordData]]:
        """The records to export from a database."""
        if self._records is None:
            self._records = self._fetch_exportable_records()

        return self._records

    @property
    def templates_path(self) -> Path:
        """Path to the templates folder."""
        return self.config.path.parent / "templates"

    @property
    def module_path(self) -> Path:
        """Path to the module folder."""
        return self.args.path / self.args.name

    def get_template_path(self, template: str) -> Path:
        """Get the path to a template, recursively browsing inherits until a file is found.
        :param template: The name of the template to get the path for.
        :return: The path to the template.
        """
        for inherit in reversed([*self.config.inherits, str(self.config.version)]):
            path: Path = self.templates_path / inherit / self.args.type / template

            if path.is_file():
                return path
        else:
            raise self.error(f"Template {template!r} not found")

    def _check_version(self) -> None:
        """Check if the Odoo version to generate code in is compatible with
        the version of the database we are exporting.
        """
        if self.args.version and OdooVersion(self.args.version) != self.database.version:
            logger.warning(
                f"The Odoo version {self.args.version!s} you are generating code for "
                f"does not match the database version {self.database.version!s}"
            )
            if not console.confirm("Do you want to continue?", default=False):
                raise self.error("Command aborted due to versions mismatch")

    def _create_module_folder(self) -> None:
        """Create the module folder for the scaffolded module if this is possible."""
        if self.module_path.exists():
            folder_status = (
                "and is not empty" if self.module_path.is_file() or list(self.module_path.iterdir()) else "but is empty"
            )
            logger.warning(f"Module folder {self.module_path!s} already exists {folder_status}")

            if not console.confirm("Do you want to overwrite it?", default=False):
                raise self.error("Command aborted due to existing module folder")

        shutil.rmtree(self.module_path, ignore_errors=True)
        self.module_path.mkdir(parents=True, exist_ok=True)

    def _get_ref_ids(self, model: str, ids: Sequence[int]) -> List[str]:
        """Find the XML ID of an existing record in the database.
        :param model: Model the record belongs to.
        :param ids: IDs of the records in the database.
        :return: The XML ID of the record or its ID if not found.
        """
        xml_ids = self.database.rpc["ir.model.data"].search_read(
            [
                ("model", "=", model),
                ("res_id", "in", list(ids)),
            ],
            fields=["res_id", "module", "name"],
        )

        ids_found: Set[int] = {xml_id["res_id"] for xml_id in xml_ids}
        ids_not_found: Set[int] = set(ids) - ids_found
        return [f"{xml_id['module']}.{xml_id['name']}" for xml_id in xml_ids] + [
            str(res_id) for res_id in ids_not_found
        ]

    def _reset_data(self) -> None:
        """Reset the data to generate the code with."""
        self._data = None
        self._records = None

    def _export_data(self) -> None:
        """Export the data from the database to the module folder."""
        models = [key for key in self.records.keys() if key in self.models and self.records[key]]

        for model in models:
            with progress.spinner(f"Exporting data from model {model!r}"):
                self._export_model_data(model, [record["res_id"] for record in self.records[model]])

    def _export_model_data(self, model: str, ids: Sequence[int]) -> None:
        """Export the data from a model to the module folder.
        :param model: The model to export the data from.
        :param ids: The ids of the records to export.
        :return: A list of dictionaries containing data of the external IDs that were exported.
        """
        model_fields: MutableMapping[str, MutableMapping[str, Union[str, bool]]] = self.database.rpc[model].fields_get()

        if not model_fields:
            raise self.error(f"Model {model!r} does not exist in database {self.database.name!r}")

        # Before Odoo 16.0, the fields_get method does not return the name of the fields
        if any("name" not in field for field in model_fields.values()):
            for name, field in model_fields.items():
                field["name"] = name

        excluded_fields: Set[str] = {
            field["name"]
            for field in model_fields.values()
            if field.get("relation", False)
            and field["name"] not in self.config["models"].get(model, {}).get("include_relations", [])
        } | {"write_date", "create_date"}
        storable_fields: List[str] = list(
            {field["name"] for field in model_fields.values() if field["store"]} - excluded_fields
        )

        if not storable_fields:
            raise self.error(f"Model {model!r} does not contain any storable fields")

        records: List[RecordData] = self.database.rpc[model].search_read([("id", "in", ids)], fields=storable_fields)

        for field in filter(lambda f: f["name"] in storable_fields and f.get("relation", False), model_fields.values()):
            for record in filter(lambda r: r[field["name"]], records):
                if field["type"] == "many2one":
                    record[field["name"]] = self._get_ref_ids(field["relation"], [record[field["name"]][0]])[0]
                else:
                    record[field["name"]] = self._get_ref_ids(field["relation"], record[field["name"]])

        if records:
            self._data["models"][model].extend(records)

    def _fetch_exportable_records(self) -> List[RecordData]:
        """Fetch the ir.model.data of the records that can be exported.
        :return: A list of dictionaries containing data of the external IDs that can be exported.
        """
        with progress.spinner("Fetching exportable records"):

            # Find records with an existing XML ID
            IrModelData = self.database.rpc["ir.model.data"]
            records_data: List[RecordData] = IrModelData.search_read(
                [
                    ("module", "in", self.args.modules),
                    ("model", "in", self.models),
                ],
                fields=["module", "model", "res_id", "name", "noupdate"],
            )

            if not records_data:
                raise self.error("No data to export")

            cached_sql_ids: MutableMapping[str, Set[int]] = defaultdict(set)
            ir_model_data: MutableMapping[str, List[RecordData]] = defaultdict(list)

            for record in records_data:
                cached_sql_ids[record["model"]].add(record["res_id"])

                # Filter models selected in the command line
                if record["module"] in self.args.modules and (
                    not self.args.models or record["model"] in self.args.models
                ):
                    ir_model_data[record["model"]].append(
                        {
                            "module": record["module"],
                            "res_id": record["res_id"],
                            "name": record["name"],
                            "noupdate": record["noupdate"],
                        }
                    )

            # Find records with an XML ID that are not part of the exported modules
            other_records_data: List[RecordData] = IrModelData.search_read(
                [
                    ("module", "not in", self._modules),
                    ("model", "in", list(self.models)),
                ],
                fields=["model", "res_id"],
            )

            for other_record in other_records_data:
                cached_sql_ids[other_record["model"]].add(other_record["res_id"])

            # Find records with no XML ID but that are part of the exported models
            for model in self.models:
                other_records_data: List[RecordData] = self.database.rpc[model].search_read(
                    [("id", "not in", list(cached_sql_ids[model]))],
                    fields=["id"],
                )

                for other_record in other_records_data:
                    ir_model_data[model].append(
                        {
                            "module": DEFAULT_MODULE_EXPORT,
                            "res_id": other_record["id"],
                            "name": f"{self.sanitize_name(model)}_{other_record['id']}_{string.suid()}",
                            "noupdate": True,
                        }
                    )

        logger.info(
            f"Module {self.args.modules[0]!r}: {sum([len(records) for records in ir_model_data.values()])} records "
            f"to export in {len(ir_model_data.keys())} models"
        )

        return ir_model_data

    def _get_file_name(self, config: MutableMapping[str, Any], data: MutableMapping[str, Any]) -> Tuple[str, str]:
        """Find the name for a file that needs to be generated and its extension.
        :param config: The config to find the name for.
        :param data: The data to find the name for.
        :return: A tuple of strings containing the name of the file to generate and its extension.
        """
        lang = config.get("lang", "txt")
        suffix = config.get("file_name_suffix", "")

        if isinstance(lang, dict):
            lang = lang[self.args.type]

        if "file_name" in config:
            return ".".join([config["file_name"] + suffix, lang]), lang

        if "file_name_by_fields" not in config:
            raise self.error(
                f"""
                Config does not contain a 'file_name' or 'file_name_by_fields' key
                {config}
                """
            )

        data_copy = data.copy()

        for field in config["file_name_by_fields"]:
            assert isinstance(field, str)

            for key in field.split("."):
                data_copy_type = type(data_copy)

                if (data_copy_type == list and key.isdigit()) or (data_copy_type == dict and key in data_copy):
                    usable_key = int(key) if data_copy_type == list else key

                    if isinstance(data_copy[usable_key], (str, int)) and not isinstance(data_copy[usable_key], bool):
                        name = str(data_copy[usable_key])
                        file_name = self.sanitize_model(name) if lang == "csv" else self.sanitize_name(name)
                        return ".".join([file_name + suffix, lang]), lang

                    if isinstance(data_copy[usable_key], (list, dict)):
                        data_copy = data_copy[usable_key]

        raise self.error(f"""Could not find a name for the file to generate: {data['__xml_id']!r}""")

    def render_template(
        self, config: MutableMapping[str, Any], data: Union[MutableMapping[str, Any], List[MutableMapping[str, Any]]]
    ) -> None:
        """Render a template.
        :param config: The config to render the template with.
        :param data: The data to render the template with.
        """

        folder_path = self.module_path / config.get("folder_name", "")

        if isinstance(data, list):
            records_by_file = defaultdict(list)

            for record in data:
                file_name, lang = self._get_file_name(config, record)
                records_by_file[file_name].append(record)
        else:
            file_name, lang = self._get_file_name(config, data)
            records_by_file = {file_name: data}

        for file_name, records in records_by_file.items():
            file_path = folder_path / file_name
            template_path = self.get_template_path(config["template"])
            template = Template(
                name=file_name,
                path=template_path,
                lang=Path(file_name).suffix.lstrip("."),
                data=records,
                filters={
                    "odoo_model": self.sanitize_model,
                    "odoo_field": self.sanitize_field_python,
                    "odoo_field_saas": self.sanitize_field_xml,
                    "odoo_field_name": self.sanitize_name,
                    "odoo_domain": self.sanitize_domain,
                    "odoo_server_action": self.sanitize_server_action,
                    "odoo_link": self.sanitize_ref,
                },
            )

            folder_path.mkdir(parents=True, exist_ok=True)
            rendered = template.render(
                pretty=self.args.pretty
                and ((lang == "py" and self.args.pretty_python) or (lang == "xml" and self.args.pretty_xml)),
                run_isort=self.args.pretty_import,
                run_autoflake=self.args.autoflake,
                line_length=self.args.line_length,
            )

            template.save(rendered, file_path)

    # TODO: postprocess data to add migrations to scripts
    # def generate_pre_migrate(self, model: str, field: str = None) -> None:
    #     """Add a pre-migration script to the manifest.
    #     :param model: The model to add the pre-migration script for.
    #     :param field: The field to add the pre-migration script for.
    #     """
    #     if field is None and model.startswith("x_"):
    #         self.migration["pre_migrate"]["models"].append({
    #             "old": model,
    #             "new": self.sanitize_model(model),
    #         })

    #     elif field.startswith("x_"):
    #         self.migration["pre_migrate"]["fields"].append({
    #             "old": field,
    #             "new": self.sanitize_name(field),
    #             "model": self.sanitize_name(model),
    #         })

    def _prefill_data(self) -> None:
        """Prefill the data to generate the code with, with default values."""
        self._prefill_data_manifest()
        self._prefill_data_init()
        self._prefill_data_migrations()
        self._prefill_data_requirements()
        self._prefill_data_project_files()
        self._prefill_data_models()

    def _prefill_data_manifest(self) -> None:
        """Generate the manifest for the module to generate code for."""
        name = self.args.modules[0] if self.args.modules else self.args.name
        title = name.replace("_", " ").title()
        module_info = self.database.rpc["ir.module.module"].search_read(
            [("name", "=", name)],
            fields=[
                "category_id",
                "author",
                "website",
                "license",
                "summary",
                "description",
                "application",
                "auto_install",
            ],
            limit=1,
        )

        if not module_info:
            if self.args.modules != DEFAULT_MODULE_LIST:
                raise self.error(f"Module {name!r} does not exist in database {self.database.name!r}")

            module_info = [{}]

        module_info = module_info[0]

        self.data["manifest"].update(
            {
                "name": name,
                "summary": module_info.get("summary", title),
                "description": module_info.get("description", title),
                "version": f"{self.version.major}.{self.version.minor}.1.0.0",
                "category": module_info.get("category_id", [0, "Uncategorized"])[1],
                "author": module_info.get("author", "Odoo PS"),
                "website": module_info.get("website", "https://www.odoo.com"),
                "license": module_info.get("license", "OEEL-1"),
                "depends": set(),
                "data": set(),
                "demo": set(),
                "qweb": set(),
                "assets": defaultdict(list),
                "pre_init_hook": False,
                "post_init_hook": False,
                "application": False,
                "installable": module_info.get("installable", True),
                "auto_install": module_info.get("auto_install", False),
                "uninstall": False,
            }
        )

    def _prefill_data_init(self) -> None:
        """Generate the init config for the module to generate code for."""
        self.data["init"].update(
            {
                "imports": set(),
                "pre_init_hook": [],
                "post_init_hook": [],
                "uninstall": [],
            }
        )

    def _prefill_data_migrations(self) -> None:
        """Generate the migration scripts configuration for the scaffolded module."""
        self.data.update(
            {
                "pre_migrate": {
                    "models": [],
                    "fields": [],
                    "remove_view": set(),
                    "lines": [],
                },
                "post_migrate": {
                    "lines": [],
                },
                "end_migrate": {
                    "lines": [],
                },
            }
        )

    def _prefill_data_requirements(self) -> None:
        """Generate the requirements configuration for the scaffolded module."""
        self.data["requirements"].update({"libs": set()})

    def _prefill_data_project_files(self) -> None:
        """List the project files to copy for the scaffolded module.
        Files must be stored in the templates folder and will be copied to the parent folder
        of the module.
        """
        self.data["project_files"] = self.config["project_files"].get("files", [])

    def _prefill_data_models(self) -> None:
        """Generate the models configuration for the scaffolded module."""
        self.data["models"] = {model: [] for model in self.models}

    def _postprocess_data(self) -> None:
        """Postprocess the data to generate the code with, making it compatible with
        the formats expected to generate templates.
        """
        self._postprocess_data_models()
        self._postprocess_data_manifest()
        self._postprocess_data_init()
        self._postprocess_data_requirements()
        self._postprocess_data_readme()

    def _postprocess_data_models(self) -> None:
        """Postprocess the models data to generate the code with."""
        for model, records in self.data["models"].items():
            if not records:
                continue

            config, _ = self.get_config_and_data("models", model)
            records_by_file = defaultdict(list)

            self._postprocess_data_model_ir_rule(model, records)

            for record in records:
                record_data = next(filter(lambda r: r["res_id"] == record["id"], self.records[model]))
                record.update(
                    {
                        "__xml_model": model,
                        "__xml_module": record_data["module"],
                        "__xml_id": f"{record_data['module']}.{record_data['name']}",
                        "__xml_name": record_data["name"],
                        "__xml_noupdate": record_data["noupdate"],
                    }
                )

                file_name, lang = self._get_file_name(config, record)
                records_by_file[file_name].append(record)

                if lang in ["xml", "csv", "sql"]:
                    self.data["manifest"]["data"].add("/".join([config["folder_name"], file_name]))

            self._postprocess_data_model_ir_model(model, records)

    def _postprocess_data_model_ir_rule(self, model: str, records: List[RecordData]) -> None:
        """Postprocess the ir.rule data to generate the code with.
        :param model: The model to postprocess the data for.
        :param records: The records to postprocess the data for.
        """
        if model != "ir.rule":
            return

        for record in records:
            record["model_name"] = self.convert_model_id_to_name(record["model_id"])

    def _postprocess_data_model_ir_model(self, model: str, records: List[RecordData]) -> None:
        """Postprocess the ir.model data to generate the code with.
        :param model: The model to postprocess the data for.
        :param records: The records to postprocess the data for.
        """
        if model != "ir.model" or not records:
            return

        self.data["init"]["imports"].add("models")

        mail_field_names = [
            field["name"]
            for field in self.database.rpc["ir.model.fields"].search_read(
                [("model", "in", ["mail.thread", "mail.activity.mixin"])],
                fields=["name"],
            )
        ]

        field_ids = [
            field["res_id"]
            for field in self.database.rpc["ir.model.data"].search_read(
                [("model", "=", "ir.model.fields"), ("module", "=", records[0]["__xml_module"])],
                fields=["res_id"],
            )
        ]

        constraint_ids = [
            constraint["res_id"]
            for constraint in self.database.rpc["ir.model.data"].search_read(
                [("model", "=", "ir.model.constraint"), ("module", "=", records[0]["__xml_module"])],
                fields=["res_id"],
            )
        ]

        for record in records:
            record["fields"] = self.database.rpc["ir.model.fields"].search_read(
                [("id", "in", field_ids), ("model_id", "=", record["id"]), ("name", "not in", mail_field_names)],
                fields=[],
                order="ttype asc, name asc",
            )

            record["sql_constraints"] = self.database.rpc["ir.model.constraint"].search_read(
                [("id", "in", constraint_ids), ("model", "=", record["id"]), ("type", "=", "u")],
                fields=["name", "definition", "message"],
            )

            record["inherited"] = (
                self.database.rpc["ir.model.data"].search_count(
                    [("model", "=", "ir.model"), ("res_id", "=", record["id"])]
                )
                > 1
            )

    def _postprocess_data_manifest(self) -> None:
        """Postprocess the manifest data to generate the code with."""
        _, data = self.get_config_and_data("manifest")
        data.update(
            {
                "depends": sorted(data["depends"]),
                "data": sorted(path.replace("\\", "/") for path in data["data"]),
                "demo": sorted(path.replace("\\", "/") for path in data["demo"]),
            }
        )

    def _postprocess_data_init(self) -> None:
        """Postprocess the init data to generate the code with."""
        _, data = self.get_config_and_data("init")
        data["imports"] = sorted(data["imports"])

    def _postprocess_data_requirements(self) -> None:
        """Postprocess the requirements data to generate the code with."""
        _, data = self.get_config_and_data("requirements")
        data["libs"] = sorted(data["libs"])

    def _postprocess_data_readme(self) -> None:
        """Postprocess the README data to generate the code with."""
        _, data = self.get_config_and_data("manifest")
        self.data["readme"]["name"] = data["name"]

    def get_config_and_data(
        self, key: str, subkey: str = None
    ) -> Tuple[MutableMapping[str, Any], Union[List[MutableMapping[str, Any]], MutableMapping[str, Any]]]:
        """Get the config and data for a given key.
        :param key: The key to get the config and data for.
        :return: The config and data for the given key.
        """
        if subkey is not None:
            config, data = self.config[key][subkey if subkey in self.config[key] else "default"], self.data[key][subkey]
        else:
            config, data = self.config[key], self.data[key]

        return config, data

    def generate_manifest(self) -> None:
        """Generate the manifest for the scaffolded module."""
        config, data = self.get_config_and_data("manifest")
        self.render_template(config, data)

    def generate_init(self) -> None:
        """Generate the init file for the scaffolded module."""
        config, data = self.get_config_and_data("init")
        self.render_template(config, data)

        if self.args.type == "sh":
            for folder in data["imports"]:
                assert isinstance(folder, str)
                folder_config = config.copy()
                folder_config["folder_name"] = folder
                self.render_template(
                    folder_config, {"imports": sorted(file.stem for file in (self.module_path / folder).iterdir())}
                )

    def generate_migrations(self) -> None:
        """Generate the migration scripts for the scaffolded module."""
        if self.args.type == "saas":
            return

        for key in ["pre_migrate", "post_migrate", "end_migrate"]:
            config, data = self.get_config_and_data(key)
            do_generate: bool = bool(data.get("lines"))
            config = config.copy()
            config["folder_name"] = config["folder_name"].format(
                version=self.get_config_and_data("manifest")[1]["version"],
            )

            if key == "pre_migrate":
                for subkey in set(data.keys()) - {"lines"}:
                    do_generate = do_generate or bool(data[subkey])

            if do_generate:
                self.render_template(config, data[key])

    def generate_requirements(self) -> None:
        """Generate the requirements file for the scaffolded module."""
        config, data = self.get_config_and_data("requirements")

        if data["libs"]:
            self.render_template(config, data)

    def generate_project_files(self) -> None:
        """Generate the project files for the scaffolded module."""
        _, data = self.get_config_and_data("project_files")

        for file in data:
            path = self.templates_path / file

            if not path.is_file():
                raise self.error(f"Project file {file!r} does not exist or is not a file")

            shutil.copy(path, self.module_path.parent / file)

    def generate_readme(self) -> None:
        """Generate the README file for the scaffolded module."""
        config, data = self.get_config_and_data("readme")
        self.render_template(config, data)

    def generate_data(self) -> None:
        """Generate the data files for the scaffolded module."""
        for model, records in self.data["models"].items():
            if not records:
                continue

            config, data = self.get_config_and_data("models", model)

            with progress.spinner(f"Generating data for {len(data)} records in model {model!r}"):
                self.render_template(config, data)

    def generate_icon(self) -> None:
        """Generate the icon for the scaffolded module."""
        icon_path = self.module_path / "static" / "description" / "icon.png"
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        imgkit.from_url(
            output_path=icon_path.as_posix(),
            options=ICON_OPTIONS,
            url=urlunparse(
                [
                    "https",
                    "ps-tools.odoo.com",
                    "/icon",
                    None,
                    urlencode({"color": random.choice(ICON_COLORS), "class_name": ""}),
                    None,
                ]
            ),
        )

    def generate_modules(self) -> None:
        """Generate the scaffolded modules."""
        self._check_version()

        if not self.models:
            raise self.error("No models to export")

        modules_list = string.join_and([f"{module!r}" for module in self._modules])
        models_list = string.join_bullet([f"{model!r}" for model in self.models])
        logger.info(
            f"Exporting data from database {self.database.name!r} for modules {modules_list} and models:\n{models_list}"
        )

        with progress.spinner("Generating module files"):
            for module in self._modules:
                self.args.modules = [module]
                self.args.name = module
                self._reset_data()
                self._create_module_folder()

                self.generate_requirements()
                self.generate_project_files()

                self.generate_data()

                self.generate_manifest()
                self.generate_readme()
                self.generate_icon()

                self.generate_init()
                self.generate_migrations()
