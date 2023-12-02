"""Find the shortest path between two models in a database using the BFS algorithm."""

# import ast

from odev.common.commands import OdoobinShellScriptCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PathfinderCommand(OdoobinShellScriptCommand):
    """Delete assets files from the database."""

    name = "assets"

    @property
    def script_run_after(self) -> str:
        return "regenerate_assets(env)"