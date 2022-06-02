import os
import re
from argparse import Namespace
from collections import defaultdict
from typing import Any
from xmlrpc.client import Fault as xmlrpc_Fault

import lxml.etree as ET
import tldextract

from odev.structures import actions, commands
from odev.utils import logging
from odev.utils.exporter import Config


_logger = logging.getLogger(__name__)

DEFAULT_MODULE_LIST = ["__export_module__", "studio_customization"]


class ExportCommand(commands.ExportCommand, commands.LocalDatabaseCommand):
    """
    Export module from a Odoo db in python or saas
    """

    name = "export"
    database_required = False
    exporter_subcommand = "export"
    arguments = [
        {
            "aliases": ["url"],
            "default": "http://localhost:8069",
            "help": "Database URL",
        },
        {
            "aliases": ["-l", "--login"],
            "dest": "user",
            "default": "admin",
            "help": "Username used for the JsonRpc connection",
        },
        {
            "aliases": ["-p", "--password"],
            "dest": "password",
            "default": "admin",
            "help": "Password  for the JsonRpc connection",
        },
        {
            "aliases": ["-m", "--modules"],
            "dest": "modules",
            "action": actions.CommaSplitAction,
            "default": DEFAULT_MODULE_LIST,
            "help": "Comma-separated list of modules to export",
        },
        {
            "aliases": ["--models"],
            "action": actions.CommaSplitAction,
            "help": "Comma-separated list of models to include",
        },
        {
            "aliases": ["--regex-off"],
            "action": "store_true",
            "dest": "regex_off",
            "help": "Regex off",
        },
    ]

    cache_xmlid: dict = defaultdict(lambda: defaultdict(list))
    xmlrpc: Any

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.args.modules = list(set(DEFAULT_MODULE_LIST + self.args.modules))

        no_cache_extract = tldextract.TLDExtract(cache_dir=False)
        url_extract = no_cache_extract(self.args.url)

        if not self.args.database:
            self.args.database = url_extract.subdomain

        url = ".".join(part for part in url_extract if part)
        is_local_url = url in {"localhost", "127.0.0.1"}
        if port_match := re.search(r":(\d{2,})", self.args.url):
            port = int(port_match.group(1))
        elif is_local_url:
            # companies are like penis: standard odoo port
            port = 8069
        else:
            # standard SSL: better to be safe than sorry
            port = 443
        protocol = "jsonrpc" if is_local_url else "jsonrpcs"

        self.export_config = Config(self.version, os.path.dirname(os.path.abspath(__file__)))
        self.init_connection(url, self.args.database, self.args.user, self.args.password, protocol=protocol, port=port)

    def run(self):
        _logger.info(
            f"Starting the export of {','.join(self.args.modules)} from "
            f"{self.args.url} into "
            f"{'xml' if self.args.type == 'saas' else 'python'} module(s)"
        )
        _logger.info("All the data (from specific models) without an XmlId will also be exported")

        try:
            self.export()
        except Exception as exception:
            _logger.error(exception)
            return 1

        _logger.success(f"Export completed successfully into {self.args.path}!")

        return 0

    def export(self):
        self.safe_mkdir(self.args.path)

        cfg = self.export_config.config["base_model"]
        exportable_ids = self.get_exportable_ids()

        # Export for each module
        for module in exportable_ids.keys():
            self._init_config(module)

            # Export each models
            for model_name in exportable_ids[module]:
                # Check if this model need to be exported ( to avoid exporting included models )
                cfg_name = model_name if model_name in self.export_config.config["base_model"] else "default"
                cfg = self.export_config.config["base_model"][cfg_name]

                if "export" not in cfg or cfg["export"] is not False:
                    # Search all id to export
                    domain = [("id", "in", list(exportable_ids[module][model_name]))]
                    data = self.get_data(cfg, model_name, domain)

                    if data:
                        # For each data, generate the corresponding template
                        if "split" in cfg and cfg["split"]:
                            for data in data[model_name]:
                                self.generate_template(data, cfg)
                        else:
                            self.generate_template(data, cfg)

            # Write __init__.py
            self._generate_init()

            # Write __manifest__.py
            self._generate_manifest()

            # Write migration script
            self._generate_mig_script()

    def safe_read_ids(self, model_name, ids):
        model = self.connection.get_model(model_name)
        try:
            yield from model.read(ids)
        except xmlrpc_Fault:
            _logger.warning("Error while reading ids at once, trying iterating")
            for id_ in ids:
                try:
                    yield self.xmlrpc.read(model_name, [id_])
                except xmlrpc_Fault as exc:
                    # TODO: Add the error to some custom report?
                    _logger.warning(f'Error while reading "{model_name}" record id={id_}:\n' f"{exc.faultString}")

    # This method returns data related to one model and its children ( include_model )
    def get_data(self, cfg, model_name, domain, with_include=True, same_module=False, order=None):
        result = defaultdict(list)

        # If there is a exclude_domain add it to the domain
        if "exclude_domain" in cfg:
            domain.append(eval(cfg["exclude_domain"])[0])

        # Define order passed to the xmlrpc class
        order = cfg.get("order", order) or {}

        # For each individual id on model_name get all the field
        model = self.connection.get_model(model_name)
        ids = model.search(domain, order=order)

        for data in self.safe_read_ids(model_name, ids):
            renamed = False
            # Workaround in 9, data can be a list and not a dict
            if type(data) == list:
                data = data[0]

            # Get ir.model.data field
            imd = self._get_xml_id(model_name, data["id"], same_module, data.get("state", "custo"))

            if (same_module and imd["module"] == self.module_name) or not same_module:

                if imd["module"] == self.module_name:
                    xml_id = imd["name"]
                else:
                    xml_id = f"{imd['module']}.{imd['name']}"

                data.update(
                    {
                        "xml_id": xml_id,
                        "noupdate": imd["noupdate"],
                        "xml_name": imd["name"],
                        "ir_model_name": model_name,
                    }
                )

                _logger.info(
                    f"Export : {self.module_name} {model_name} ({data['id']}) -> {imd['module']}.{imd['name']}"
                )

                # If model_name has child , override data with data from child
                if "includes" in cfg and with_include:
                    self._includes_model(cfg, data)

                # And now do the magic regex :
                if not self.args.regex_off:
                    renamed = self._call_regex(model_name, data)

                # Call callback method
                if "callback" in cfg and with_include:
                    for fct in cfg["callback"]:
                        getattr(self, fct)(data)

                if model_name == "ir.model" and with_include:
                    # TODO : Use configuration instead of hardcoding model
                    file_name = re.sub(r"[\W.]", "", data["model"].replace(".", "_").replace("x_", ""))
                    self.init["class"].add(file_name)
                    self._check_and_add_migrate("model", data["model"])

                    data.update({"import": self._check_import(data)})

                if model_name == "ir.model.fields":
                    self._check_and_add_migrate("field", data["model"], data["name"])

                merged = False
                # If some regex have been applied to the model, check if the new ( renamed )
                # need to be merge into a existing one
                if renamed:
                    merged = self.merge(result.get(model_name), data, cfg)

                if not merged:
                    result[model_name].append(data)

        return result

    def merge(self, tab, data, cfg):
        if not tab:
            return

        merge_to = [d for d in tab if d["xml_id"] == data["xml_id"]]

        for m in merge_to:
            for inc in cfg.get("includes"):
                m[inc["key"]].extend(data[inc["key"]])

        return bool(merge_to)

    def get_exportable_ids(self):
        ir_data = defaultdict(list)
        exportable_ids = []
        ids = defaultdict(lambda: defaultdict(set))

        _logger.info("Get all ids to export")
        _logger.warning("Can take some times to finish.")

        ir_model_data = self.connection.get_model("ir.model.data")
        exportable_ids = ir_model_data.search_read(
            [("module", "in", self.args.modules)], fields=["res_id", "model", "module"]
        )
        all_know_ir_data_ids = ir_model_data.search_read(
            [("model", "in", self.export_config.all_models)],
            fields=["res_id", "model", "module", "name", "noupdate"],
            order="id asc",
        )

        # Tab of all ids to export
        for res_id in all_know_ir_data_ids:
            ir_data[res_id["model"]].append(res_id["res_id"])

            if not res_id["res_id"] in self.cache_xmlid[res_id["model"]]:
                self.cache_xmlid[res_id["model"]][res_id["res_id"]] = {
                    "module": res_id["module"],
                    "name": res_id["name"],
                    "noupdate": res_id["noupdate"],
                    "state": None,
                }

        # All data without xml_id
        for model_name, ir_id in ir_data.items():
            model = self.connection.get_model(model_name)
            model_ids = model.search_read([("id", "not in", ir_id)], fields=["id"])

            for model_id in model_ids:
                exportable_ids.append({"model": model_name, "res_id": model_id["id"], "module": "__export_module__"})

        # Load all IDS related to the modules in self.include_module
        # If models is passed as args only take id from these models
        for item in exportable_ids:
            if not self.args.models or item["model"] in self.args.models:
                ids[item["module"]][item["model"]].add(int(item["res_id"]))

        # Include oprhan in main dict of ids to export
        for model_name in self.export_config.included_models:
            model = self.connection.get_model(model_name)

            cfg = self.export_config.config["base_model"][model_name]
            inc = self.export_config._get_parent_include(cfg["parent"], model_name)
            assert inc is not None
            inverse_field = inc["inverse_name"]

            for module in ids.keys():
                parent_ids = model.search_read(
                    [("id", "in", list(ids[module][model_name]))], fields=[inverse_field], order="id asc"
                )
                ids[module][cfg["parent"]].update({int(x["model_id"][0]) for x in parent_ids})

        return ids

    def _get_odoo_xml(self, data):
        parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)
        root = ET.fromstring(data["arch"].encode(), parser)
        odoo_xml = ""

        # TODO : Necessary ?
        xml = root
        if root.tag == "odoo":
            xml = root.find("./data")
        elif root.tag == "data":
            for node in root:
                odoo_xml += ET.tostring(
                    node,
                    encoding="utf-8",  # type: ignore
                    pretty_print="True",  # type: ignore
                    xml_declaration=False,  # type: ignore
                ).decode("utf-8")

        if odoo_xml == "":
            odoo_xml = ET.tostring(
                xml,
                encoding="utf-8",  # type: ignore
                pretty_print=True,  # type: ignore
                xml_declaration=False,  # type: ignore
            ).decode("utf-8")

        odoo_xml = self._parse_action(odoo_xml)

        data["arch"] = odoo_xml

    def _parse_action(self, xml):

        for action_id in set(re.findall(r"[\"'>]([0-9]+)[\"'<]", xml)):
            xml_id = self.cache_xmlid["ir.actions.server"][int(action_id)]

            if xml_id:
                xml = re.sub(
                    r"([\"'>]){}([\"'<])".format(action_id),
                    r"\1%({}.{})d\2".format(xml_id["module"], xml_id["name"]),
                    xml,
                )

        return xml

    def _includes_model(self, cfg, data):
        for inc in cfg["includes"]:
            rec_id = None
            comodel_name = None
            is_reference = "is_reference" in inc and inc["is_reference"]
            same_module = "same_module" in inc and inc["same_module"]

            if inc["key"] in data:
                if data[inc["key"]]:
                    if is_reference:
                        comodel_name, rec_id = data[inc["key"]].split(",")
                    elif type(data[inc["key"]]) == int:
                        rec_id = data[inc["key"]]
                    else:
                        rec_id = data[inc["key"]][0]
            elif "field" in inc and inc["field"] in data:
                rec_id = data[inc["field"]]

            if rec_id:
                if not comodel_name:
                    comodel_name = inc["comodel_name"]

                domain = [(inc["inverse_name"], "=", rec_id)]

                if "domain" in inc:
                    domain.append(eval(inc["domain"]))

                order = {}
                if comodel_name in self.export_config.config["base_model"]:
                    order = self.export_config.config["base_model"][comodel_name].get("order", "")

                try:
                    include_data = self.get_data(cfg, comodel_name, domain, False, same_module, order)[comodel_name]

                    data[inc["key"]] = include_data
                except Exception as e:
                    _logger.error(e)

    def _get_xml_id(self, model_name, res_id, same_module, state):
        xml_id = None

        if model_name in self.cache_xmlid:
            if res_id in self.cache_xmlid[model_name]:
                xml_id = self.cache_xmlid[model_name][res_id]

        if not xml_id:
            # We already know xml_id if resources to export
            # Here we only try to get xml id for external resources
            if model_name not in self.export_config.exportable_models:
                imd = self.connection.get_model("ir.model.data")
                imd_id = imd.search_read(
                    [("model", "=", model_name), ("res_id", "=", res_id)],
                    fields=["module", "name", "noupdate"],
                    order="id asc",
                    limit=1,
                )

                if imd_id:
                    xml_id = {
                        "module": imd_id[0]["module"],
                        "name": imd_id[0]["name"],
                        "noupdate": imd_id[0]["noupdate"],
                    }

            if not xml_id:
                xml_id = {"module": "__export_module__", "name": f"{model_name}_{res_id}", "noupdate": False}

            self.cache_xmlid[model_name][res_id] = xml_id

        if not same_module and xml_id["module"] != self.module_name:
            self.depends.append({"module": xml_id["module"], "state": state})

        return xml_id

    def _call_regex(self, model_name, data):
        renamed = False
        cfg = self.export_config.config["regexp"].get(model_name, []) + self.export_config.config["regexp"].get("*", [])

        for regex in cfg:
            for field in regex["fields"]:
                for r in regex["regexp"]:
                    if field in data:
                        if type(data[field]) == str:
                            renamed = True
                            data.update(
                                {
                                    field: re.sub(
                                        r["pattern"].replace("\\\\", "\\"),
                                        r["replace"].replace("\\\\", "\\"),
                                        data[field],
                                    )
                                }
                            )
                        elif type(data[field]) in [dict]:
                            renamed = True
                            for key, value in data[field].item():
                                data[field][key] = data.update({field: re.sub(r["pattern"], r["replace"], value)})

        return renamed

    def _init_config(self, module_name):
        super()._init_config()

        module = self.connection.get_model("ir.module.module")

        module_info = module.search_read(
            [("name", "=", module_name)],
            fields=[
                "summary",
                "description",
                "icon",
                "latest_version",
                "license",
                "author",
                "shortdesc",
                "category_id",
            ],
        )

        self.module_name = module_name
        self.depends = []

        if module_info:
            self.manifest["author"] = module_info[0]["author"]
            self.manifest["license"] = module_info[0]["license"]
            self.manifest["icon"] = module_info[0]["icon"]
            self.manifest["description"] = module_info[0]["description"] or ""
            self.manifest["name"] = module_info[0]["shortdesc"]
            self.manifest["summary"] = module_info[0]["summary"] or ""
            self.manifest["category"] = module_info[0]["category_id"]

    def _check_import(self, data):
        text = ""
        lib = []

        for ias in data.get("ir.actions.server", []):
            text += ias["code"]

        for field in data.get("ir.model.fields", []):
            if field["compute"]:
                text += field["compute"]

        search_index = [
            {"import_lib": "from odoo.exceptions import Warning", "keywords": ["raise Warning("]},
            {"import_lib": "from odoo.exceptions import UserError", "keywords": ["UserError("]},
            {"import_lib": "from odoo.http import request", "keywords": ["request."]},
            {"import_lib": "import requests", "keywords": ["requests."]},
            {"import_lib": "import json", "keywords": ["json."]},
        ]

        for know_lib in search_index:
            if any(word in text for word in know_lib["keywords"]):
                lib.append(know_lib["import_lib"])

        return lib

    def _generate_manifest(self):
        has_other_base_module = bool(
            [m["module"] for m in self.depends if m["module"] != "base" and m["state"] == "base"]
        )

        for m in self.depends:
            if has_other_base_module and m["module"] != "base" or not has_other_base_module:
                self.manifest["depends"].add(m["module"])

        super()._generate_manifest()
