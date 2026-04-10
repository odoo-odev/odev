import re


class ReMatch:
    """A string that can be compared to a regular expression."""

    def __init__(self, pattern: re.Pattern[str]):
        self.pattern = pattern

    def __repr__(self) -> str:
        return repr(self.pattern)

    def __eq__(self, other: str) -> bool:
        return bool(self.pattern.search(other))

    def __hash__(self) -> int:
        return hash(self.pattern.pattern)


class OdoobinMatch(ReMatch):
    """A string that can be compared to an odoo-bin command as run in the terminal."""

    def __init__(self, database_name: str, arguments: list[str] | None = None, subcommand: str | None = None):
        if arguments is None:
            arguments = []

        subcommand = f"{subcommand} " if subcommand else ""
        base_pattern = (
            rf"odoo-bin {subcommand}--database {database_name}(?:\-[\w]{{8}})? "
            rf"--addons-path [a-z0-9.\-/,]+ --log-level \w+"
        )
        # Use lookaheads to match arguments in any order
        # Each argument must be present somewhere after the base pattern
        args_lookahead = "".join(rf"(?=.*{re.escape(arg)})" for arg in arguments)
        pattern = re.compile(rf"{base_pattern}{args_lookahead}")

        super().__init__(pattern)
