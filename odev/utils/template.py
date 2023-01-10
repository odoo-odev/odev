import os
from argparse import Namespace
from typing import Any, List, MutableMapping, Optional

import autoflake
import black
import isort
import lxml.etree as ET
from jinja2 import Environment, FileSystemLoader

from odev.utils import logging
from odev.utils.exporter import (
    Config,
    odoo_domain,
    odoo_field,
    odoo_field_name,
    odoo_model,
    odoo_saas_field,
    odoo_server_action,
)


_logger = logging.getLogger(__name__)
logging.getLogger("black").setLevel(logging.logging.ERROR)
logging.getLogger("blib2to3").setLevel(logging.logging.ERROR)


class Template:
    type = "sh"
    version = None

    export_config: Optional[Config]
    export_type: str
    module_name: str
    manifest: MutableMapping[str, Any]
    args: Namespace

    def _init_config(self) -> None:
        assert self.export_config is not None
        base_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates"))
        self.template_folders: List[str] = []

        for export_type in ["saas", "sh"] if self.type == "saas" else ["sh"]:
            self.template_folders.extend(
                [
                    os.path.join(base_path, str(self.version), export_type),
                    os.path.join(
                        base_path, self.export_config.config.get("template_folder", str(self.version)), export_type
                    ),
                ]
            )

        self.env = Environment(loader=FileSystemLoader(self.template_folders), keep_trailing_newline=True)
        self.env.filters["odoo_field"] = odoo_field
        self.env.filters["odoo_field_name"] = odoo_field_name
        self.env.filters["odoo_model"] = odoo_model
        self.env.filters["odoo_saas_field"] = odoo_saas_field
        self.env.filters["odoo_server_action"] = odoo_server_action
        self.env.filters["odoo_domain"] = odoo_domain

    def generate_template(self, data, cfg):
        if not cfg:
            return

        data.update(
            {
                "export_type": self.export_type,
                "module_name": self.module_name,
                "module_version": self.version,
                "comment": self.args.comment,
            }
        )

        if "file_ext" in cfg and isinstance(cfg["file_ext"], dict):
            cfg["file_ext"] = cfg["file_ext"][self.type]

        file = self.write(self.render(data, cfg), cfg, data)

        if cfg["file_ext"] in ["csv", "sql", "xml"]:
            self.manifest["data"].add(file)

    # Method to render a template with data as argument
    def render(self, data, cfg):
        tpl = self.env.get_template(cfg["template"])
        txt = tpl.render(data=data)

        # FIXME:
        # if not self.pretty:
        #     return txt

        try:
            return self.prettier(txt, cfg, data)
        except black.NothingChanged:
            return txt
        except Exception as e:
            _logger.error(e)
            return txt

    def prettier(self, txt, cfg, data=None):

        if cfg["file_ext"] == "py" and not self.args.pretty_py_off:
            txt = black.format_str(txt, mode=black.FileMode(line_length=self.args.line_length or 9999))

            if not self.args.pretty_import_off:
                txt = isort.code(txt, force_single_line=True, single_line_exclusions=["odoo"])

            if not self.args.autoflake_off:
                filename = self._get_file_name(cfg, data)

                if filename not in ["__init__.py"]:
                    txt = autoflake.fix_code(
                        txt, remove_all_unused_imports=True, remove_duplicate_keys=True, remove_unused_variables=True
                    )

        elif cfg["file_ext"] == "xml" and not self.args.pretty_xml_off:
            parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)
            root = ET.fromstring(txt.encode(), parser)
            ET.indent(root, space=" " * 4)
            txt = ET.tostring(
                root,
                encoding="utf-8",  # type: ignore
                pretty_print=True,  # type: ignore
                xml_declaration=True,  # type: ignore
            ).decode("utf-8")

        return txt

    def write(self, txt, cfg, data=None):
        dest_path = os.path.join(self.args.path, self.module_name, cfg["folder_name"])

        if not os.path.exists(dest_path):
            os.makedirs(dest_path)

        file_name = self._get_file_name(cfg, data)
        dest = os.path.join(dest_path, file_name)

        file_mode = "a+"

        # If file exist and extension is xml, merge it
        if os.path.exists(dest):
            if cfg["file_ext"] == "xml":
                txt = self._merge_xml(dest, txt)
                file_mode = "w"
            elif cfg.get("file_name") == "requirements":
                f = open(dest, "r")
                lines = f.read().splitlines() + txt.split("\n")
                lib = sorted(set(lines), key=lines.index)
                txt = "\n".join(lib)
                file_mode = "w"

        with open(dest, file_mode) as fh:
            fh.write(txt)

        return os.path.join(cfg["folder_name"], file_name)

    def _get_file_name(self, cfg, data):
        name = cfg["file_name"] if "file_name" in cfg else ""

        if not name:
            data_cp = data.copy()
            for field in cfg["split_name_field"]:
                for key in field.split("."):
                    key = int(key) if type(data_cp) == list else key

                    if (type(data_cp) == list and data_cp[key]) or (type(data_cp) == dict and key in data_cp):
                        if type(data_cp[key]) in [str, bool, int]:
                            if data_cp[key]:
                                name = data_cp[key]
                                break
                        else:
                            data_cp = data_cp[key]

        name = self.env.from_string(name).render(data)
        file_name = f"{odoo_field(name.replace('.','_'))}.{cfg['file_ext']}"

        # to avoid issue with access rule in csv; no '_' in filename
        if cfg["file_ext"] == "csv":
            file_name = name + "." + cfg["file_ext"]

        return file_name

    def _merge_xml(self, file_path, txt):
        try:
            parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)
            root = ET.parse(file_path, parser).getroot()

            for elem in ET.fromstring(txt.encode(), parser).xpath("//odoo/*"):
                root.append(elem)

            ET.indent(root, space="    ")
            return ET.tostring(
                root,
                encoding="utf-8",  # type: ignore
                pretty_print=True,  # type: ignore
                xml_declaration=True,  # type: ignore
            ).decode("utf-8")
        except Exception as e:
            raise ValueError(f'Failed merging xml in "{file_path}" with:\n{txt}') from e
