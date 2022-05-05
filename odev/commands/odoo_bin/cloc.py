import csv
import io
import re
from subprocess import CompletedProcess
from textwrap import indent

from texttable import Texttable

from odev.commands.odoo_bin import run
from odev.utils import logging
from odev.utils.logging import term


_logger = logging.getLogger(__name__)


class ClocCommand(run.RunCommand):
    """
    Count the lines of code in custom modules.
    """

    name = "cloc"
    odoobin_subcommand = "cloc"

    arguments = [
        {
            "aliases": ["--csv"],
            "dest": "csv",
            "action": "store_true",
            "help": "Format output as csv",
        },
    ]

    def run(self):
        self.check_database()

        if not self.addons:
            _logger.warning(
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise\n",
            )

        odoo_result: CompletedProcess = self.run_odoo(print_cmdline=not self.args.csv)
        result = odoo_result.stdout

        split = re.split(r"\n-+", result)
        split_lines = re.split(r"\s{2,}", split[~1].lstrip().replace("\n", " " * 2))
        split_totals = re.split(r"\s+", split[~0].strip())

        table_headers = ["Odoo cloc", "Lines", "Other", "Code"]
        table_align = ["l"] + ["r" for _ in table_headers[1:]]
        table_rows = [
            [indent(split_lines[i], " " * 2) if re.match(r"^(/|[a-z.]+/\d+)", split_lines[i]) else split_lines[i]]
            + split_lines[i + 1 : i + 4]
            for i in range(0, len(split_lines), 4)
        ] + [["", *split_totals]]
        if not self.args.csv:
            table = Texttable()
            table.set_deco(Texttable.HEADER)
            table.set_max_width(term.width - 4)
            table.set_header_align(table_align)
            table.set_cols_align(table_align)
            table.add_rows([table_headers] + table_rows)

            table_text = table.draw() or ""
            table_separator = (re.search(r"\n(=+)\n", table_text) or [])[0].strip()
            table_text_split = table_text.replace(table_separator, term.snow4(table_separator)).split("\n")
            table_text_split.insert(len(table_text_split) - 1, term.snow4(table_separator.replace("=", "-")))

            print("\n" + indent("\n".join(table_text_split), " " * 2), end="")
        else:
            output_buffer = io.StringIO()
            writer = csv.DictWriter(output_buffer, table_headers)
            writer.writeheader()
            dict_rows = ({colname: value for colname, value in zip(table_headers, values)} for values in table_rows)
            writer.writerows(dict_rows)
            for line in output_buffer.getvalue().splitlines():
                print(line)

        return 0
