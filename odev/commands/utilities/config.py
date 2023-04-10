"""Get or set odev configuration values."""

from typing import Any, List, MutableMapping

from odev.common.commands import Command
from odev.common.console import Colors


TABLE_HEADERS: List[MutableMapping[str, Any]] = [
    {"name": "", "style": "bold", "min_width": 15},
    {"name": ""},
]


class ConfigCommand(Command):
    """Get or set configuration values."""

    name = "config"
    aliases = ["conf"]

    arguments = [
        {
            "name": "key",
            "help": "Configuration key to fetch, in the format 'section.option'.",
            "nargs": "?",
        },
        {
            "name": "value",
            "help": "Value to set for the given key.",
            "nargs": "?",
        },
    ]

    def run(self):
        if self.args.key is None:
            self.print_config()
        else:
            if "." in self.args.key:
                section, key = self.args.key.split(".", 1)
            else:
                section, key = self.args.key, None

            if self.args.value is None:
                self.print_config(section=section, key=key)
            else:
                self.set_config(section=section, key=key)
                self.print_config(section=section, key=key)

    def print_config(self, section: str = None, key: str = None):
        """Print the entire configuration."""
        config = self.config.dict()

        if section is not None:
            if section not in config:
                raise self.error(f"Section '{section}' does not exist")

            config = {section: config[section]}

        for config_section in config:
            if key is not None and key not in config[config_section]:
                raise self.error(f"Key '{key}' does not exist in section '{config_section}'")

            self.print_table(
                [
                    [config_key, config_value]
                    for config_key, config_value in config[config_section].items()
                    if key is None or config_key == key
                ],
                config_section,
            )

    def print_table(self, rows: List[List[str]], name: str = None, style: str = None):
        """Print a table.
        :param rows: The table rows.
        :param name: The table name.
        :type rows: List[List[str]]
        """
        self.print()

        if name is not None:
            if style is None:
                style = f"bold {Colors.CYAN}"

            rule_char: str = "─"
            title: str = f"{rule_char} [{style}]{name}[/{style}]"
            self.console.rule(title, align="left", style="", characters=rule_char)

        self.table([{**header} for header in TABLE_HEADERS], rows, show_header=False, box=None)

    def set_config(self, section: str, key: str):
        """Set a configuration value."""
        config = self.config.dict()

        if section not in config:
            raise self.error(f"Section '{section}' does not exist")

        if key not in config[section]:
            raise self.error(f"Key '{key}' does not exist in section '{section}'")

        try:
            setattr(getattr(self.config, section), key, self.args.value)
        except (AssertionError, ValueError) as error:
            raise self.error(str(error))
