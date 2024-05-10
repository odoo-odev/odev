"""Find the shortest path between two models in a database using the BFS algorithm."""

import ast
from typing import List, Tuple

from odev.common import args, string
from odev.common.commands import OdoobinShellScriptCommand
from odev.common.console import TableHeader


class PathfinderCommand(OdoobinShellScriptCommand):
    """Find the shortest path between two models in a database using a BFS algorithm."""

    _name = "pathfinder"
    _aliases = ["pf"]

    origin = args.String(description="Model to start from.")
    destination = args.String(description="Model to end at.")

    @property
    def script_run_after(self) -> str:
        return f"pathfinder(env, {self.args.origin!r}, {self.args.destination!r})"

    def run_script_handle_result(self, result: str):
        """Handle the result of the script execution."""
        paths: List[List[Tuple[str, str, str]]] = ast.literal_eval(result)
        headers = [
            TableHeader(align="right", style="color.black"),
            TableHeader(min_width=30),
            TableHeader(min_width=30),
            TableHeader(style="color.black"),
        ]

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
            self.table(headers, rows, title=f"{'.'.join(chain)} {details}")

        self.console.clear_line()
