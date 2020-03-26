"""Get or set odev configuration values."""

from typing import Any, List, MutableMapping, Optional

from odev.common import args, string
from odev.common.commands import Command
from odev.common.console import Colors


TABLE_HEADERS: List[MutableMapping[str, Any]] = [
    {"name": "", "style": "bold", "min_width": 15},
    {"name": "", "min_width": 30},
    {"name": "", "style": Colors.BLACK},
]


class ConfigCommand(Command):
    """Get or set configuration values."""

    _name = "config"
    _aliases = ["conf"]

    key = args.String(description="Configuration key to fetch, in the format 'section.option'.", nargs="?")
    value = args.String(description="Value to set for the given key.", nargs="?")

    def run(self):
        try:
            if self.args.key is None:
                self.print_config()
            else:
                section, key = self.args.key.split(".", 1) if "." in self.args.key else (self.args.key, None)

                if self.args.value is not None:
                    if key is None:
                        raise self.error("You must specify a key to set a value")

                    self.config.set(section, key, self.args.value)

                self.print_config(section=section, key=key)
        except KeyError as error:
            raise self.error(str(error.args[0])) from error

    def print_config(self, section: Optional[str] = None, key: Optional[str] = None):
        """Print the entire configuration."""
        config = self.config.to_dict()

        if section is not None:
            self.config.check_attribute(section)
            config = {section: config[section]}

        for config_section in config:
            self.config.check_attribute(config_section, key)
            self.print_table(
                [
                    [
                        config_key,
                        config_value,
                        string.normalize_indent(
                            getattr(getattr(self.config, config_section).__class__, config_key).__doc__
                        ),
                    ]
                    for config_key, config_value in config[config_section].items()
                    if key is None or config_key == key
                ],
                config_section,
            )

    def print_table(self, rows: List[List[str]], name: Optional[str] = None, style: Optional[str] = None):
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

        TABLE_HEADERS[-1]["width"] = self.console.width - sum(header["min_width"] for header in TABLE_HEADERS[:-1])
        self.table([{**header} for header in TABLE_HEADERS], rows, show_header=False, box=None)
