import os
import re
import shlex
import subprocess
from textwrap import indent

from texttable import Texttable

from odev.commands.odoo_bin import run
from odev.constants import ODOO_ADDON_PATHS
from odev.utils import logging, odoo
from odev.utils.logging import term


_logger = logging.getLogger(__name__)


class ClocCommand(run.RunCommand):
    """
    Count the lines of code in custom modules.
    """

    name = "cloc"
    odoobin_subcommand = "cloc"

    def run(self):
        self.check_database()

        if not self.addons:
            _logger.warning(
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise\n",
            )

        version = self.db_version_clean()

        repos_path = self.config["odev"].get("paths", "odoo")
        version_path = odoo.repos_version_path(repos_path, version)
        odoobin = os.path.join(version_path, "odoo/odoo-bin")

        addons = [version_path + addon_path for addon_path in ODOO_ADDON_PATHS]
        addons += [os.getcwd(), *self.addons]
        addons = [path for path in addons if odoo.is_addon_path(path)]

        python_exec = os.path.join(version_path, "venv/bin/python")
        addons_path = ",".join(addons)
        command_args = [
            python_exec,
            odoobin,
            *("-d", self.database),
            f"--addons-path={addons_path}",
            *self.additional_args,
        ]

        if self.odoobin_subcommand:
            command_args.insert(2, self.odoobin_subcommand)

        command = shlex.join(command_args)
        _logger.info(f"Running: {command}")
        result = subprocess.getoutput(command)

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
        return 0
