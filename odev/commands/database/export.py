"""Export data from a database."""

import re
from typing import List, MutableMapping, Union, cast

from odev.common import progress
from odev.common.commands import DatabaseCommand
from odev.common.connectors.rpc import Model
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class ExportCommand(DatabaseCommand):
    """Export data from a database."""

    name = "export"
    aliases = ["search", "read", "records"]

    arguments = [
        {
            "name": "model",
            "aliases": ["-m", "--model"],
            "help": "The model to export.",
            "required": True,
        },
        {
            "name": "domain",
            "aliases": ["-d", "--domain"],
            "help": "The domain to filter the records to export.",
            "action": "store_eval",
            "default": [],
        },
        {
            "name": "fields",
            "aliases": ["-F", "--fields"],
            "help": "The fields to export, all fields by default.",
            "action": "store_comma_split",
            "default": [],
        },
        {
            "name": "format",
            "aliases": ["-t", "--format"],
            "help": "The output format.",
            "choices": ["txt", "json", "csv", "xml", "py"],
            "default": "txt",
        },
        {
            "name": "output",
            "aliases": ["-o", "--output"],
            "help": "Path to the output file.",
            "action": "store_path",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.args.output is not None and self.args.output.is_dir():
            file_name = re.sub(r"[^a-zA-Z0-9]", "_", f"{self.database.name}_{self.args.model}")
            self.args.output /= f"{file_name}.{self.args.format}"

        if self.args.output is not None:
            self.args.output = self.args.output.resolve()

    def run(self):
        with progress.spinner(f"Searching records in {self.args.model}"):
            model = self.database.models[self.args.model]
            record_ids = model.search(self.args.domain)

        with progress.spinner(f"Exporting {len(record_ids)} records"):
            match self.args.format:
                case "json":
                    data = model._convert_json(record_ids, self.args.fields)
                    self.console.code(data, "json", file=self.args.output)
                case "csv":
                    data = model._convert_csv(record_ids, self.args.fields)
                    self.console.code(data, "csv", file=self.args.output)
                case "xml":
                    data = model._convert_xml(record_ids, self.args.fields)
                    self.console.code(data, "xml", file=self.args.output)
                # case "py":
                #     data = model._export_python()
                #     self.console.code(data, "python", file=self.args.output)
                case _:
                    self.output_txt(record_ids, model)

        if self.args.output is not None:
            logger.info(f"Exported {len(record_ids)} records to {self.args.output}")

    def output_txt(self, ids: List[int], model: Model):
        """Format the records as a table.
        :param ids: The record IDs to output
        :param model: The model to output
        :return: The formatted table
        """

        def __relation(_model: str, _ids: Union[int, List[int]]) -> str:
            if isinstance(_ids, int):
                _ids = [_ids]
            return f"{_model}({', '.join([str(id_) for id_ in _ids])}{',' if _ids else ''})"

        fields = list(self.args.fields or model.fields.keys())
        records = model.read(ids, fields=fields)
        columns: List[MutableMapping[str, str]] = []
        rows: List[List[str]] = []

        for field in fields:
            column = {"name": f"{model.fields[field]['string']} ({field})"}

            if model.fields[field]["type"] in ["integer", "float", "monetary"]:
                column["justify"] = "right"

            columns.append(column)

            for idx, record in enumerate(records):
                if idx == len(rows):
                    rows.append([])

                match model.fields[field]["type"]:
                    case "many2one" | "one2many" | "many2many":
                        value = (
                            ""
                            if not record[field]
                            else __relation(
                                cast(str, model.fields[field]["relation"]), cast(Union[int, List[int]], record[field])
                            )
                        )
                    case "boolean":
                        value = str(record[field])
                    case _:
                        value = "" if record[field] is False else str(record[field])

                rows[idx].append(value)

        self.table(columns=columns, rows=rows, file=self.args.output)
