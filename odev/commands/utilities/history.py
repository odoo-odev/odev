"""Check the history of odev commands run."""

import sys

from odev.common import args
from odev.common.commands import Command
from odev.common.console import TableHeader
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class HistoryCommand(Command):
    """Check the history of odev commands run in the past."""

    _name = "history"

    command = args.String(aliases=["-c", "--command"], description="The command to check the history of.")
    clear = args.Flag(aliases=["-C", "--clear"], description="Clear the history.")

    def run(self) -> None:
        if self.args.clear:
            self.clear_history()
            return

        self.show_history()

    def clear_history(self) -> None:
        """Erase all existing records in the history."""
        logger.info("Clearing history")
        return self.store.history.clear()

    def show_history(self) -> None:
        """Show the history of a command, or the whole history."""
        history = self.store.history.get(command=self.args.command)

        if not history:
            raise self.error(
                f"No history available for {f'command {self.args.command!r}' if self.args.command else 'all commands'}"
            )

        headers = [
            TableHeader("ID", align="right"),
            TableHeader("Command"),
            TableHeader("Date"),
        ]
        rows = [
            [str(line.id), f"{sys.argv[0]} {line.command} {line.arguments}", line.date.strftime("%Y-%m-%d %X")]
            for line in history
        ]

        self.print()
        self.table(headers, rows, title="Commands History")
        self.console.clear_line()
