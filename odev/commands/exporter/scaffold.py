import os
import re
from argparse import Namespace
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import pre_commit.constants as C
import tldextract
from packaging.version import Version
from pre_commit.commands.install_uninstall import install

from odev.constants import LAST_ODOO_VERSION, PSTOOLS_DB, PSTOOLS_PASSWORD, PSTOOLS_USER
from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.credentials import CredentialsHelper
from odev.utils.exporter import Config, odoo_field, odoo_field_name, odoo_model
from odev.utils.github import is_git_repo


_logger = logging.getLogger(__name__)


REPO_NAME = {1: "psbe-custom", 2: "pshk-custom", 3: "psae-custom", 4: "psus-custom", 5: "psus-custom"}


class ScaffoldCommand(commands.ExportCommand, commands.LocalDatabaseCommand):
    """
    Scaffold the module code of a Quickstart task based on the analysis made with the ps-tools
    """

    name = "scaffold"
    database_required = False
    exporter_subcommand = "scaffold"
    version: Version

    arguments = [
        {
            "aliases": ["task_id"],
            "help": "Ps-tools or Odoo.com task id to generate",
        },
        {
            "aliases": ["-e", "--env"],
            "choices": ["prod", "staging"],
            "default": "prod",
            "help": "Default database to use (use staging for test)",
        },
    ]

    analysis: Mapping[str, Any]
    export_type = "scaffold"

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.module_name = args.name

        no_cache_extract = tldextract.TLDExtract(cache_dir=False)

        url_info = no_cache_extract(args.source) if "source" in self.args else None
        self.database = url_info.subdomain if url_info else self.args.database or "[CLIENT_NAME]"

        connection = PSTOOLS_DB[self.args.env]
        self.init_connection(connection["url"], connection["db"], PSTOOLS_USER, PSTOOLS_PASSWORD)

    def run(self):
        _logger.info(f"Generate scaffold code for analysis : {self.args.task_id}")

        try:
            self.analysis = self.get_analysis()
            self._init_config()

            if self.args.path == ".":
                _logger.info("Trying to generate a logical addons-path")
                self.args.path = self._get_default_path()

            self.export()

            if is_git_repo(self.args.path):
                _logger.info("Pre-commit hook installation")
                install(
                    config_file=C.CONFIG_FILE,
                    store=True,  # type: ignore
                    hook_types=["pre-commit"],
                    git_dir=Path(self.args.path, ".git"),
                )
            else:
                self.print_info()
        except Exception as exception:
            _logger.error(exception)
            return 1

        _logger.success("Scaffold generated. Hope it will help you !")

        return 0

    def get_analysis(self) -> Mapping[str, Any]:
        analysis = self.connection.get_model("presales.analysis")

        analysis_ids = analysis.search_read(
            ["|", ("id", "=", self.args.task_id), ("task_id", "=", self.args.task_id)],
            order="write_date desc",
        )

        if not analysis_ids:
            raise Exception(f"Cannot find any analysis with id : {self.args.task_id}")
        elif len(analysis_ids) == 1:
            return analysis_ids[0]
        else:
            ask = f"Multiple analysis found with id : {self.args.task_id}"
            ask += f"\n{' ' * 4}".join(
                f"    {i+1}) {analysis_ids[i]['name']} ({analysis_ids[i]['id']})" for i in range(len(analysis_ids))
            )

            _logger.warning(ask)
            index = _logger.ask("Please select the good one", "1", list(map(str, range(1, len(analysis_ids) + 1))))

            return analysis_ids[int(index) - 1]

    def _init_config(self) -> None:
        self.export_config = Config(self.version, os.path.dirname(os.path.abspath(__file__)))

        super()._init_config()

        if not self.version:
            self.version = Version(odoo.get_odoo_version(self.analysis["version"][1] or LAST_ODOO_VERSION))

        if not self.args.type:
            self.type = "saas" if self.analysis["platform"] == "saas" else "sh"

        self.manifest["name"] = self.args.name.replace("_", " ").title()
        self.manifest["summary"] = f"{self.manifest['name']} scaffolded module"
        self.manifest["version"] = str(self._get_version(short=False))
        self.manifest["task_id"] = self.analysis["task_id"]

    def _get_default_path(self) -> str:
        saas_repo_name = REPO_NAME.get(self.analysis["company_id"][0], "psbe-custom")
        countries_prefix = {id: country.split("-")[0] for id, country in REPO_NAME.items()}
        country_prefix = countries_prefix.get(self.analysis["company_id"][0], "psbe")
        branch_name = repo_name = ""

        if self.type == "saas":
            repo_name = saas_repo_name
            branch_name = f"{self.analysis['version'][1]}-{self.database}"
        else:
            repo_name = (
                f"{country_prefix}-{self.database}"
                if not [c for c in countries_prefix.values() if c in self.database]
                else self.database
            )

        return os.path.join(self.config["odev"].get("paths", "dev"), "odoo-ps", repo_name, branch_name)

    def export(self) -> None:
        _logger.info(
            f"Ps-Tools DB : Scaffold analysis {self.analysis['name']} "
            f"({self.analysis['task_id']}) into {self.args.path}"
        )
        self.safe_mkdir(self.args.path, self.args.name)

        models = self._generate_data_models()
        self._generate_unit_test(models)
        self._generate_backend_views()
        self._generate_security()
        self._generate_report()
        self._generate_controller()
        self._generate_assets()
        self._generate_data()
        self._generate_script()
        self._generate_mig_script()
        self._generate_manifest()
        self._generate_init()
        self._generate_icon()
        self._copy_files()

        analysis = self.connection.get_model("presales.analysis")
        analysis.write(self.analysis["id"], {"state": "scaffolded"})

    def print_info(self):

        if self.type == "sh":
            remote_git = "git@github.com:odoo-ps/[CLIENT_REPO].git"
        else:
            remote_git = f"git@github.com:odoo-ps/{REPO_NAME.get(self.analysis['company_id'][0], 'psbe-custom')}.git"

        github_user = CredentialsHelper().get("github.user", "GitHub username:")

        if github_user:
            gh_user_part = re.split("[-@]", github_user)

            if gh_user_part:
                github_user = gh_user_part[0]

        domain = self.database.replace("-", "_").lower()

        _logger.info(
            "\n\t".join(
                [
                    "Generation done, now you can use those commands to init the github repo :\n",
                    f"cd {os.path.join(self.args.path)}",
                    "git init",
                    f"git remote add origin {remote_git}",
                    f"git checkout -b {self.export_config.version}-{domain}-{self.analysis['task_id']}-{github_user}",
                    "git submodule add git@github.com:odoo-ps/psbe-internal.git"
                    if self.analysis["integration_line_ids"]
                    else "",
                    "git pull origin main",
                    "pre-commit install",
                ]
            )
        )

    def _generate_data_models(self):
        _logger.debug("Generate data models")
        fields = self.connection.get_model("presales.field_line")
        fields_ids = fields.search_read(
            [("id", "in", self.analysis["field_line_ids"])], order="type, is_compute, field_name"
        )

        # Because a override can be set on a model without a line in
        # Data model, we need to create a models dict with prefilled models
        # This method also returns all the computes to be added on each field
        models, computes = self._load_business_flow()
        # Same for integration
        models.update(self._generate_integration(self.analysis["integration_line_ids"]))

        for field in fields_ids:
            model = odoo_field_name(field["model"])

            if self.type == "sh":
                self._check_and_add_migrate("model", model)
                self._check_and_add_migrate("field", model, field["field_name"])

            if model not in models:
                all_fields = list(filter(lambda f: f["model"] == model, fields_ids))
                models[model] = self._add_new_model(model, field["model_type"], all_fields)
            else:
                # Need to override state because a field can be "Existing"
                # on data model, but with "Add" in "Business flow"
                models[model]["state"] = "inherit" if field["model_type"] == "existing" else "manual"

            if models[model]["state"] == "inherit":
                self._add_depends(odoo_model(model))

            # Split on field_name to allow multiple field in one line on the presale app
            for f in re.split(", ", field["field_name"]):
                f_name = odoo_field_name(f)
                selection = "[()]"
                compute = ""
                depends = ""

                if model in computes and f_name in computes[model]:
                    compute = computes[model][f_name]["description"]
                    depends = computes[model][f_name]["depends"]

                field_desc = field["description"]
                if f:
                    field_desc = re.sub(r"_id[s]?", "", odoo_field(f)).replace("_", " ").capitalize()

                if field["type"][1] == "selection" and field["description"] and "," in str(field["description"]):
                    selection = [
                        (odoo_field_name(x.strip()), x.strip().capitalize()) for x in field["description"].split(",")
                    ]
                    field["description"] = ""

                domain = ""
                if field["domain"]:
                    domain = field["domain"]
                elif field["description"]:
                    res = re.match(r".*(\[[ ]*\(.*?\)]*[ ]*\]).*", field["description"])
                    if res:
                        domain = res.group(1)

                models[model]["ir.model.fields"].append(
                    {
                        "name": f_name,
                        "model": odoo_model(model),
                        "ttype": field["type"][1],
                        "description": field["description"],
                        "field_description": field_desc,
                        "relation": field["comodel_name"] or "",
                        "relation_table": field["relation"],
                        "column1": field["column1"],
                        "column2": field["column2"],
                        "relation_field": field["inverse_name"],
                        "inverse": field["inverse_function"],
                        "index": field["index"],
                        "compute": compute or False,
                        "depends": depends if depends else False,
                        "selection": selection,
                        "store": field["is_stored"],
                        "readonly": field["is_readonly"],
                        "required": field["is_required"],
                        "track_visibility": field["is_tracked"],
                        "related": field["related_field"],
                        "default_value": field["default_value"],
                        "xml_id": odoo_field_name(model + "_" + f_name),
                        "domain": domain,
                    }
                )

        cfg = self.export_config.config["base_model"]["ir.model"]

        for model in models.values():
            if self.type == "saas" and not model["ir.model.fields"]:
                continue

            self.generate_template(model, cfg)

        self.init["class"] = models.keys()

        return models

    def _load_business_flow(self):
        business_flow = self.connection.get_model("presales.business_flow_line")
        business_flow_line_ids = business_flow.search_read([("id", "in", self.analysis["business_flow_line_ids"])])
        models = defaultdict()
        compute = defaultdict(lambda: defaultdict())
        lib = set()

        for business in business_flow_line_ids:
            business_type = business["type"][1]
            field = odoo_field_name(business["name"])

            for m in business["model"].split(","):
                model = odoo_field_name(m)

                xml_id = f"{self.module_name}.{odoo_field_name(business['name'])}"
                xml_id_model = f"{self.module_name}.{odoo_field_name(business['model'])}"

                if business_type in ["method", "compute", "constraint", "cron"] and model not in models:
                    models[model] = self._add_new_model(model, business["action"])

                if business_type in ["method", "cron"]:
                    models[model]["method"].append(
                        {
                            "name": odoo_field_name(field),
                            "description": business["description"],
                            "action": business["action"],
                        }
                    )

                    if business_type == "cron":
                        cfg = self.export_config.config["base_model"]["ir.cron"]
                        data = {
                            "xml_id": f"{xml_id}_cron",
                            "res_model": odoo_field_name(business["model"]),
                            "name": odoo_field(business["name"] or "").replace("_", " ").strip().capitalize(),
                            "ative": True,
                            "doall": False,
                            "numbercall": -1,
                            "interval_number": 1,
                            "interval_type": "day",
                            "model_id": [{"xml_id": xml_id_model}],
                            "description": business["description"],
                            "code": f"model.{business['name']}()",
                        }

                        if self.type == "saas":
                            data.update(
                                {
                                    "code": (
                                        f"{odoo_field_name(business['model'])}_action = "
                                        f"ref(\"{self.module_name}.{odoo_field_name(business['model'])}_action\")"
                                        f"{odoo_field_name(business['model'])}_action.run()"
                                    )
                                }
                            )

                        self.generate_template(data, cfg)
                elif business_type == "compute":
                    compute[model][field] = {
                        "description": business["description"] or "",
                        "depends": business["depends_fields"] or "",
                    }
                elif business_type == "external_lib":
                    lib.update(set(re.split(", ", business["name"])))
                elif business_type in ["base_automation", "on_change"]:
                    cfg = self.export_config.config["base_model"]["base.automation"]

                    data = {
                        "xml_id": xml_id,
                        "name": business["name"] or "",
                        "model": ["", business["model"]],
                        "description": business["description"],
                        "model_id": [{"xml_id": xml_id_model}],
                        "trigger": business_type if business_type == "on_change" else "",
                        "state": "code" if business_type == "on_change" else "",
                    }

                    if self.type == "saas":
                        cfg["folder_name"] = "data/automation"

                    self.generate_template(data, cfg)

                if business_type == "server_action" or (business_type == "cron" and self.type == "saas"):
                    cfg = self.export_config.config["base_model"]["ir.actions.server"]

                    code = f"""
<![CDATA[
for rec in records:
    rec.{business["name"]}()
]]>"""

                    data = {
                        "xml_id": f"{xml_id}_action",
                        "name": business["name"],
                        "model_name": business["model"],
                        "model_id": [{"xml_id": xml_id_model}],
                        "binding_model_id": [{"xml_id": xml_id_model}],
                        "biding_view_types": "form,list",
                        "description": business["description"],
                        "state": "code",
                        "code": code,
                    }

                    if self.type == "saas":
                        cfg["folder_name"] = "data/automation"

                    self.generate_template(data, cfg)
                elif business_type == "constraint":
                    models[model]["constraints"].append(
                        {"name": field or "field", "constraint": business["description"]}
                    )

        if lib and self.type == "sh":
            cfg = self.export_config.config["requirements"]
            self.generate_template({"lib": lib}, cfg)

        return [models, compute]

    def _add_depends(self, model):
        special_case = {"res": ""}
        module = model.split(".")

        module = module[0] if module else model

        if module in special_case:
            module = special_case[module]

        if module:
            self.manifest["depends"].add(module)

    def _add_new_model(self, model, model_state, fields=None):
        return {
            "model": odoo_model(model),
            "xml_id": f"{self.module_name}.{odoo_field_name(model)}",
            "name": model.replace("_", " ").capitalize(),
            "state": "inherit" if model_state in ["override", "existing"] else "manual",
            "transient": "wizard" in model,
            "ir.model.fields": [],
            "integration": defaultdict(dict),
            "constraints": [],
            "method": [],
            "is_mail_thread": any(f.get("inherit_mail_thread", False) for f in (fields or [])),
            "is_mail_activity": any(f.get("inherit_mail_activity_mixin", False) for f in (fields or [])),
        }

    def _generate_backend_views(self):
        _logger.debug("Generate backend views")
        data_type = self.connection.get_model("presales.data_type")
        all_view_types = {
            data_type["id"]: data_type["name"]
            for data_type in data_type.search_read([("model_id", "=", "List of backend view change")], ["name"])
        }

        backend_line = self.connection.get_model("presales.backend_line")
        backend_views_ids = backend_line.search_read([("id", "in", self.analysis["backend_line_ids"])])
        views = defaultdict(dict)

        for view in backend_views_ids:
            if view["action"] == "add" or view["action"] == "edit":
                view_types = view["view_type"] or [41]  # 41 : Form

                for type_view in view_types:
                    xml_id = view["view"] or (view["model"] + "_" + all_view_types[type_view])
                    uniq_key = odoo_field_name(f"{view['model']}_{xml_id}_{str(type_view)}")

                    if uniq_key not in views:
                        data = {
                            "xml_id": odoo_field_name(xml_id),
                            "name": xml_id.replace(".", " ").replace("_", " ").capitalize(),
                            "model": odoo_model(view["model"]),
                            "inherit_id": [{"xml_id": odoo_field_name(xml_id)}],
                            "arch": "",
                            "description": [f"{view['description'] or ''} {view['field'] or ''}"],
                            "fields": view["field"].split(",") if view["field"] else [],
                        }

                        views[uniq_key] = data
                    elif "description" in view or "field" in view:
                        views[uniq_key]["description"].append(  # type: ignore
                            f"{view['description'] or ''} {view['field'] or ''}"
                        )

            elif view["action"] == "delete":
                self.migration_script["pre_migrate"]["remove_view"].add(view["view"])
            elif view["action"] == "menu":

                if view["view"]:
                    xml_id = view["view"] if "menu_" in view["view"] else f"menu_{view['view']}"
                else:
                    xml_id = f"menu_{odoo_field(view['display_name'])}"

                if view["menu_action"]:
                    data = {
                        "xml_id": odoo_field_name(view["menu_action"]),
                        "name": view["name"],
                        "res_model": odoo_model(view["model"]),
                        "view_mode": ",".join(
                            [all_view_types[k].lower() for k in view["view_type"] if k in all_view_types]
                        ),
                        "action": view["menu_action"],
                        "groups_id": view["groups"],
                        "type": "ir.actions.act_window",
                    }

                    cfg = self.export_config.config["base_model"]["ir.actions.act_window"]
                    cfg.update({"folder_name": "views", "file_name": "menu"})

                    self.generate_template(data, cfg)

                data = {
                    "ir.ui.menu": [
                        {
                            "xml_id": odoo_field_name(xml_id),
                            "name": view["name"],
                            "parent_id": [{"xml_id": view["parent_id"]}],
                            "action": [{"xml_id": view["menu_action"] or ""}],
                            "groups_id": view["groups"],
                        }
                    ],
                }

                cfg = self.export_config.config["base_model"]["ir.ui.menu"]
                self.generate_template(data, cfg)

        cfg = self.export_config.config["base_model"]["ir.ui.view"]

        for view in views.values():
            view["description"] = "\n".join(view.get("description", ""))  # type: ignore
            self.generate_template(view, cfg)

    def _generate_security(self):
        _logger.debug("Generate security files")
        security_line = self.connection.get_model("presales.security_line")
        security_line_ids = security_line.search_read([("id", "in", self.analysis["security_line_ids"])])

        security = {"ir.model.access": [], "ir.rule": [], "res.groups": []}

        for line in security_line_ids:
            if line["type"] == "acl":

                model = odoo_field_name(line["model"])

                security["ir.model.access"].append(
                    {
                        "xml_id": model,
                        "name": line["name"],
                        "model_id": [{"xml_id": f"model_{model}"}],
                        "group_id": [{"xml_id": line["groups"]}],
                        "perm_read": line["as_read_access"],
                        "perm_write": line["as_write_access"],
                        "perm_create": line["as_create_access"],
                        "perm_unlink": line["as_delete_access"],
                    }
                )
            elif line["type"] == "record_rules":
                security["ir.rule"].append(
                    {
                        "xml_id": line["model"],
                        "name": line["name"],
                        "model_id": [{"xml_id": f"model_{line['model']}"}],
                        "groups": [{"xml_id": grp} for grp in (line["groups"] or "").split(",")],
                        "global": False,
                        "domain_force": line["domain"],
                        "perm_read": line["as_read_access"],
                        "perm_write": line["as_write_access"],
                        "perm_create": line["as_create_access"],
                        "perm_unlink": line["as_delete_access"],
                    }
                )
            elif line["type"] == "new_group":
                security["res.groups"].append(
                    {"xml_id": line["name"], "name": line["name"], "implied_ids": [], "category_id": []}
                )

        for key, data in security.items():
            if security[key]:
                cfg = self.export_config.config["base_model"][key]
                self.generate_template({key: data}, cfg)

    def _generate_report(self):
        _logger.debug("Generate report")
        report_line = self.connection.get_model("presales.report_line")
        report_line_ids = report_line.search_read([("id", "in", self.analysis["report_line_ids"])])

        for report in report_line_ids:
            cfg = self.export_config.config["report"]
            # TODO: Use include in scaffold_report
            # Also fix report view, False_document, ir.action.report ?
            report.update({"view_id": report["view"], "model": report["model"] or ""})
            self.generate_template(report, cfg)

    def _generate_controller(self):
        _logger.debug("Generate controller")

        controller_line = self.connection.get_model("presales.controller_line")
        controller_line_ids = controller_line.search_read([("id", "in", self.analysis["controller_line_ids"])])

        if controller_line_ids:
            if self.type == "saas":
                _logger.warning("Tried to generate a controller for a saas project, ignored.")
                return

            cfg = self.export_config.config["controller"]
            self.generate_template({"controllers": controller_line_ids}, cfg)

    def _generate_assets(self):
        _logger.debug("Generate js/css assets")
        assets_line = self.connection.get_model("presales.js_line")
        assets_line_ids = assets_line.search_read([("id", "in", self.analysis["js_line_ids"])])

        if assets_line_ids:
            js_cfg = self.export_config.config["default_js"]
            scss_cfg = self.export_config.config["default_scss"]

            assets = defaultdict(lambda: defaultdict(lambda: {"file_name": None, "file_path": None, "methods": []}))

            for asset in sorted(assets_line_ids, key=lambda asset: asset["type"] if "type" in asset else ""):
                file_name = os.path.basename(asset["file_path"] or "") or "None"
                file_path = os.path.dirname(asset["file_path"] or "") or "None"
                asset_type = asset.get("type", "js")
                asset_template = asset.get("assets_template", "assets_backend")

                if asset_type == "js":
                    method = {
                        "action": asset["action"],
                        "method_name": asset["name"] or "None",
                        "description": asset["description"] or "",
                    }
                    assets[asset_template][file_name]["methods"].append(method)  # type: ignore

                asset_info = {
                    "file_name": re.sub(r"(\.js|\.css|\.scss|\.saas)", "", file_name),
                    "file_path": file_path,
                    "type": asset_type,
                }

                assets[asset_template][file_name].update(asset_info)

            for asset_template, asset_files in assets.items():
                for asset in asset_files.values():
                    asset["type"] = asset.get("type", "js")  # type: ignore

                    cfg = js_cfg if asset["type"] == "js" else scss_cfg
                    self.generate_template(asset, cfg)

                    if self.version >= Version("15.0"):
                        asset_file = f"{self.args.path}/static/src/{asset['type']}/{asset['file_name']}.{asset['type']}"
                        self.manifest["assets"][asset_template].append(asset_file)

                if self.version < Version("15.0"):
                    cfg = self.export_config.config["assets"]
                    self.generate_template({"asset_template": asset_template, "assets": asset_files.values()}, cfg)

    def _generate_data(self):
        _logger.debug("Generate data")
        data_line = self.connection.get_model("presales.data_line")
        data_lines_ids = data_line.search_read([("id", "in", self.analysis["data_line_ids"])])

        cfg = self.export_config.config["base_model"]["default"]
        suffix = ""

        if self.type == "saas":
            suffix = "_data"

        for line in filter(lambda dl: dl["model"] and dl["description"], data_lines_ids):
            field_line = self.connection.get_model("presales.field_line")
            field_line_ids = field_line.search_read([("model", "=", line["model"])])

            description = line["description"] or ""

            if len(field_line_ids) == 1:
                values = description.split(",")
            else:
                values = [description]

            for value in values:
                # TODO: Add field's type for creating 'eval' 's type node for boolean and others fields
                data = dict(
                    {x["field_name"]: "" for x in field_line_ids},
                    ir_model_name=odoo_field_name(line["model"] + suffix),
                )

                if field_line_ids and field_line_ids[0]["model_type"] == "existing":
                    data.update(
                        {
                            "xml_id": self.args.name + "." + odoo_field_name(line["model"]),
                            "type": field_line_ids[0]["type"],
                        }
                    )
                else:
                    data["xml_id"] = odoo_field_name(line["model"].strip())

                if len(data) <= 3:
                    data.update(
                        {
                            "name": value.strip(),
                            "xml_id": (
                                f"{data['xml_id']}_"
                                f"{odoo_field_name(value.strip()) if len(value.strip()) < 100 else ''}"
                            ),
                        }
                    )

                self.generate_template(data, cfg)

    def _generate_script(self):
        _logger.debug("Generate script")
        script_line = self.connection.get_model("presales.script_line")
        script_line_ids = script_line.search_read([("id", "in", self.analysis["script_line_ids"])])

        actions = defaultdict(list)

        for s in script_line_ids:
            actions[s["action"]].append(
                {"model": s["model"], "field": s["field_name"], "description": s["description"]}
            )

        for action in ["pre_init_hook", "post_init_hook", "uninstall"]:
            if actions[action]:
                self.manifest[action] = True
                self.init[action] = actions[action]

        for action in ["pre_migrate", "post_migrate", "end_migrate"]:
            self.migration_script[action]["lines"] += actions[action]

        if actions["sql"]:
            self.manifest["sql"] = actions["sql"]
            sql = defaultdict(lambda: defaultdict(list))

            for line in actions["sql"]:
                sql[line["model"]]["sql"].append(
                    {"model": line["model"], "field": line["field"], "description": line["description"]}
                )

            cfg = self.export_config.config["sql"]
            for k, s in sql.items():
                self.generate_template({"model": k, "sql": s["sql"]}, cfg)

    def _generate_integration(self, integration_ids):
        _logger.debug("Generate integration")
        integration_line = self.connection.get_model("presales.integration_line")
        integration_line_ids = integration_line.search_read([("id", "in", integration_ids)])
        models = defaultdict()

        if integration_line_ids:
            integrations_type = {x["type"] for x in integration_line_ids}
            if "sftp" in integrations_type:
                self.integration = "edi_sftp_connection"
                self._add_depends("edi_sftp_connection")
            elif "ftp" in integrations_type:
                self.integration = "edi_ftp_connection"
                self._add_depends("edi_ftp_connection")
            else:
                self.integration = "edi_ftp_connection"

            self._add_depends("edi_base")

        cfg = self.export_config.config["edi_integration"]

        # Create models / type fields and methods
        for integration in integration_line_ids:
            model = odoo_field_name(integration["model"])

            if model not in models:
                models[model] = self._add_new_model(integration["model"], "existing")

                models[model]["ir.model.fields"].append(
                    {
                        "name": "type",
                        "model": odoo_model(model),
                        "ttype": "selection",
                        "compute": None,
                        "selection_add": [(odoo_field_name(integration["name"]), integration["name"].capitalize())],
                        "ondelete": {odoo_field_name(integration["name"]): "cascade"},
                        "xml_id": odoo_field_name(model + "_type"),
                    }
                )
            else:
                models[model]["ir.model.fields"][0]["selection_add"].append(
                    (odoo_field_name(integration["name"]), integration["name"].capitalize())
                )
                models[model]["ir.model.fields"][0]["ondelete"].update(
                    {odoo_field_name(integration["name"]): "cascade"}
                )

            if not odoo_field_name(integration["flow"]) in models[model]["integration"]:
                models[model]["integration"][odoo_field_name(integration["flow"])] = []

            models[model]["integration"][odoo_field_name(integration["flow"])].append(
                {
                    "name": odoo_field_name(integration["name"]),
                    "format": odoo_field_name(integration["format"]),
                    "process": integration["process"],
                }
            )

            # Create ir.filters, edi.connection, Create edi.integration
            self.generate_template(integration, cfg)

        return models

    def _generate_unit_test(self, models):
        if self.type == "sh" and self.analysis["need_unit_test"]:
            cfg = self.export_config.config["init"].copy()
            init_test_path = os.path.join(self.args.path, self.module_name, "tests")

            self.generate_template({}, self.export_config.config["unit_test_common"])

            tests_models = {
                m["model"]: {"method": m["method"], "compute": {c["name"]: c["compute"]}}
                for k, m in models.items()
                for c in m["ir.model.fields"]
                if m["method"] or c["compute"]
            }

            test_class = set()

            for model, methods in tests_models.items():
                data = [
                    {"name": re.sub(r"^_", "", m["name"], 1), "description": m["description"]}
                    for m in methods["method"]
                ]
                data = data + [{"name": f"compute_{field}", "description": ""} for field in methods["compute"]]

                self.generate_template({"model": model, "methods": data}, self.export_config.config["unit_test"])
                test_class.add(f"test_{odoo_field_name(model)}")

            cfg.update({"folder_name": init_test_path})
            self.generate_template({"class": test_class}, cfg)
