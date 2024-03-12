"""Find the shortest path between two models in a database using the BFS algorithm."""

import ast
from typing import (
    Any,
    List,
    MutableMapping,
    Optional,
    Tuple,
)

from odev.common import args, string
from odev.common.commands import OdoobinShellScriptCommand
from odev.common.console import Colors


TABLE_HEADERS: List[MutableMapping[str, Any]] = [
    {"name": "Step", "justify": "right", "style": Colors.BLACK},
    {"name": "Records", "min_width": 30},
    {"name": "Model", "min_width": 30},
    {"name": "Relation", "style": Colors.BLACK},
]


class PathfinderCommand(OdoobinShellScriptCommand):
    """Find the shortest path between two models in a database using a BFS algorithm."""

    _name = "pathfinder"
    _aliases = ["pf", "shortest_path", "sp"]

    origin = args.String(description="Model to start from.")
    destination = args.String(description="Model to end at.")

    @property
    def script_run_after(self) -> str:
        return f"pathfinder(env, {self.args.origin!r}, {self.args.destination!r})"

    def run_script_handle_result(self, result: str):
        """Handle the result of the script execution."""
        paths: List[List[Tuple[str, str, str]]] = ast.literal_eval(result)
        self.console.clear_line()

        for path in paths:
            chain: List[str] = []
            rows: List[List[str]] = []
            cardinality_from, cardinality_to = "one", "one"

            for index, (model, record, relation) in enumerate(path):
                chain.append(record)
                rows.append([str(index), record, model, relation.capitalize()])

                if not relation:
                    continue

                current_cardinality = relation.split("2", 1)

                if current_cardinality[0] == "many":
                    cardinality_from = "many"

                if current_cardinality[1] == "many":
                    cardinality_to = "many"

            cardinality: str = f"{cardinality_from}2{cardinality_to}".capitalize()
            details: str = string.stylize(f"─ {len(path) - 1} steps ─ {cardinality}", "default")
            self.print_table(rows, name=f"{'.'.join(chain)} {details}")

    def print_table(self, rows: List[List[str]], name: Optional[str] = None, style: Optional[str] = None):
        """Print a table.
        :param rows: The table rows.
        :param name: The table name.
        """
        self.print()

        if name is not None:
            if style is None:
                style = f"bold {Colors.CYAN}"

            rule_char: str = "─"
            title: str = f"{rule_char} [{style}]{name}[/{style}]"
            self.console.rule(title, align="left", style="", characters=rule_char)

        self.table([{**header} for header in TABLE_HEADERS], rows, show_header=False, box=None)
