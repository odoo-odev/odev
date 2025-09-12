import re
from typing import List, Optional


class ReMatch:
    """A string that can be compared to a regular expression."""

    def __init__(self, pattern: re.Pattern[str]):
        self.pattern = pattern

    def __repr__(self) -> str:
        return repr(self.pattern)

    def __eq__(self, other: str) -> bool:
        return bool(self.pattern.search(other))


class OdoobinMatch(ReMatch):
    """A string that can be compared to an odoo-bin command as run in the terminal."""

    def __init__(self, database_name: str, arguments: Optional[List[str]] = None, subcommand: Optional[str] = None):
        if arguments is None:
            arguments = []

        subcommand = f"{subcommand} " if subcommand else ""
        pattern = re.compile(
            rf"odoo-bin {subcommand}--database {database_name}(?:\-[\w]{{8}})? "
            rf"--addons-path [a-z0-9.\-/,]+ --log-level \w+ {' '.join(arguments)}"
        )

        super().__init__(pattern)
