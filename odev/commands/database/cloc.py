"""Count the lines of custom code in a local database."""

import csv
import re
from io import StringIO
from typing import List, MutableMapping, Optional, Sequence

from odev.common import args, string
from odev.common.commands import OdoobinCommand
from odev.common.console import Colors


class ClocCommand(OdoobinCommand):
    """Run odoo-bin cloc on a database and count custom lines of code within the installed modules."""

    name = "cloc"

    csv = args.Flag(
        aliases=["--csv"],
        help="Format output as CSV.",
    )

    re_line_details = re.compile(
        r"""
        (?:
            (?P<module>\s*[/\da-z._-]+)?
            \s+
            (?P<all>\d+)
            \s+
            (?P<other>\d+)
            \s+
            (?P<code>\d+)
        )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    """The regular expression to parse a line of the cloc output."""

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        process = self.odoobin.run(args=self.args.odoo_args, subcommand=self.name, stream=False)

        if process is None:
            raise self.error("Failed to fetch cloc result.")

        headers = [
            {"name": "Module", "justify": "left"},
            {"name": "All", "justify": "right"},
            {"name": "Other", "justify": "right"},
            {"name": "Code", "justify": "right", "style": Colors.PURPLE},
        ]
        lines, total = self.parse(process.stdout.decode())

        if not self.args.csv:
            return self.table(headers, lines, total)

        return self.print(self.format_csv([header["name"] for header in headers], [*lines, total]))

    def format_csv(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
        """Format the result as a csv string.

        :param headers: The headers of the table.
        :param rows: The rows of the table.
        :return: The formatted csv string.
        :rtype: str
        """
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()

    def parse(self, output: str):
        """Parse the result of the odoo-bin process and extract information.

        :param output: The decoded output of the odoo-bin process.
        :return: A tuple of the parsed lines and the total line.
        :rtype: Tuple[List[Dict[str, str]], Dict[str, str]]
        """
        result_lines: List[str] = output.strip().splitlines()
        total_line = result_lines[~0]
        result_lines = result_lines[2:~2]
        total = self._parse_line(total_line)

        if total is None:
            raise self.error("Cannot parse total line from cloc output.")

        lines: List[List[str]] = []
        last_module: str = ""

        for result_line in result_lines:
            parsed_line = self._parse_line(result_line)

            if parsed_line is None:
                continue

            line: List[str] = list(parsed_line.values())

            if line[0] is None:
                line[0] = ""

            if not line[0].startswith(" "):
                last_module = line[0]
                line[0] = f"[{Colors.CYAN}]{line[0]}[/{Colors.CYAN}]"
            else:
                line[0] = string.indent(re.sub(rf"^.*?/{last_module}/", "", line[0]).lstrip(), 2)

            lines.append(line)

        return lines, ["", *list(total.values())[1:]]

    def _parse_line(self, line: str) -> Optional[MutableMapping[str, str]]:
        """Parse a line of the cloc output.

        :param line: The line to parse.
        :return: The parsed line.
        :rtype: MutableMapping[str, str]
        """
        match = self.re_line_details.search(line)

        if match is None:
            return None

        return match.groupdict()
