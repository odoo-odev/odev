import json
import keyword
import os
import re
from typing import Any, List, MutableMapping

import unidecode


class Config:
    json: MutableMapping[str, Any]
    version = None
    config: MutableMapping[str, Any]
    exportable_models: List[str] = []

    def __init__(self, version, path):
        self.version = version
        json_path = os.path.join(path, "config/export.json")
        with open(json_path) as json_file:
            self.json = json.load(json_file)

        self._parse_json()

        self.all_models = list(self.config["base_model"])
        self.included_models = [x for x, y in self.config["base_model"].items() if "parent" in y]

    def _parse_json(self):
        self.config_version = self.json.get(str(self.version), "default")

        if "inherit" in self.json[self.config_version]:
            self.config = self.json[self.json[self.config_version]["inherit"]]

            self._override_config(self.json[self.config_version], self.config)
        else:
            self.config = self.json[self.config_version]

    def _override_config(self, config, override_config):
        for key in config.keys():
            if type(config[key]) == dict:
                self._override_config(config[key], override_config[key])
            elif key in override_config:
                override_config[key] = config[key]

    def _get_parent_include(self, parent, model):
        if parent in self.config["base_model"] and "includes" in self.config["base_model"][parent]:
            for include in self.config["base_model"][parent]["includes"]:
                if include["key"] == model:
                    return include


# Remove all non word characters
def odoo_field_name(field):
    if field:
        field = re.sub(r"[.\s]", "_", field).lower()
        field = re.sub(r"[\W]", "", field)
        field = re.sub(r"\_+", "_", field)
        field = re.sub(r"\_+$", "", field)
        field = unidecode.unidecode(field)

    return field


# Model use . instead of _
def odoo_model(model):
    model = str(odoo_field(model))
    model = model.replace("_", ".")
    model = re.sub(r"[\W]", ".", model)
    model = unidecode.unidecode(model)
    # replace _* by only one
    model = re.sub(r"\.+", ".", model)

    return model.lower()


def odoo_field(field):
    # TODO: Check if needed
    # if self.type == "saas":
    #     return field

    special_fields = {"x_name": "name_custo"}

    if type(field) != str or field in ["x_icon"]:
        return field
    elif field in special_fields:
        return special_fields[field]

    # Regex to filter :
    # x_data -> data
    # default_x_field_x_data -> default_field_data
    # capex_po -> capex_po
    # The other exception is already managed before ( x_icon or x_name )
    field = re.sub(r"(?<=['\W_\s])x_(studio_)?|^x_(studio_)?", r"", field)
    # record['test'] -> record.test
    field = re.sub(r"record\[['\"]?(\w*)['\"]?\]", r"record.\1", field)
    # replace _* by only one
    field = re.sub(r"(?<=[\W])_+", "_", field)
    # Replace number
    if len(field) >= 1:
        field = "_" + field if field[0].isdigit() else field

    if field in keyword.kwlist:
        field = field + "_"

    if not field:
        field = "x_"

    return field


# Saas field need to have a prefix x_
def odoo_saas_field(field):
    if field[:2] != "x_" and field[:7] != "studio_":
        field = "x_" + field

    return field


def odoo_server_action(server_action):
    server_action = server_action.replace(" env[", " self.env[")
    server_action = server_action.replace(" env", " self.env")
    server_action = server_action.replace("object.", "self.")
    server_action = server_action.replace("record.", "self.")
    server_action = server_action.replace(" model.", " self.")
    server_action = re.sub(r"([\s\W])?context([\W]?)", r"\1self.context\2", server_action)
    server_action = re.sub(r"object\[['\"]?(\w*)['\"]?\]", r"self.\1", server_action)

    if "action = " in server_action.replace("action = {...}", ""):
        server_action += "\n\n        return action"

    return server_action


def odoo_domain(data):
    data = str(data)

    # FIXME: Need to be uncommented
    # try:
    #     data = self.prettier(str(ast.literal_eval(data)), "py")
    # except Exception:
    #     self.logger.error("Aie : " + str(data))

    data = data.replace("&", "&amp;")
    data = data.replace("<", "&lt;")
    data = data.replace(">", "&gt;")
    data = data.replace('"', "'")

    return data.strip()
