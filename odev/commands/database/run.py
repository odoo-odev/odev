"""Run an Odoo database locally."""

import re

from odev.common.commands import OdoobinCommand
from odev.common.console import RICH_THEME_LOGGING, Colors
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class RunCommand(OdoobinCommand):
    """Run the odoo-bin process for the selected database locally."""

    name = "run"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.odoobin.is_running:
            raise self.error(f"Database {self.database.name!r} is already running")

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        self.odoobin.run(args=self.args.odoo_args, progress=self.odoobin_progress)

    def odoobin_progress(self, line: str):
        """Beautify odoo logs on the fly."""
        match = re.match(self._odoo_log_regex, line)

        if match is None:
            return self.print(f"[{Colors.RED}]{line}[/{Colors.RED}]")

        self.last_level = match.group("level").lower()
        level_color = (
            f"bold {Colors.GREEN}"
            if self.last_level == "info"
            else RICH_THEME_LOGGING[f"logging.level.{self.last_level}"]
        )

        self.print(
            f"[{Colors.BLACK}]{match.group('time')}[/{Colors.BLACK}] "
            f"[{level_color}]{match.group('level')}[/{level_color}] "
            f"[{Colors.PURPLE}]{match.group('database')}[/{Colors.PURPLE}] "
            f"[{Colors.BLACK}]{match.group('logger')}:[/{Colors.BLACK}] {match.group('description')}",
            highlight=False,
        )
