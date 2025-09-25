"""Get or set odev configuration values."""

from odev.common import args, string
from odev.common.commands import Command
from odev.common.console import TableHeader


class ConfigCommand(Command):
    """Get or set configuration values."""

    _name = "config"
    _aliases = ["conf", "cfg"]

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

    def print_config(self, section: str | None = None, key: str | None = None):
        """Print the entire configuration."""
        config = self.config.to_dict()
        headers = [
            TableHeader(min_width=15),
            TableHeader(min_width=30),
            TableHeader(style="color.black"),
        ]

        if section is not None:
            self.config.check_attribute(section)
            config = {section: config[section]}

        self.print()

        for config_section in config:
            self.config.check_attribute(config_section, key)

            options = [
                [
                    config_key,
                    config_value,
                    string.normalize_indent(
                        getattr(getattr(self.config, config_section).__class__, config_key).__doc__
                    ),
                ]
                for config_key, config_value in config[config_section].items()
                if hasattr(self.config, config_section) and (key is None or config_key == key)
            ]

            if options:
                self.table(headers, options, title=config_section)

        self.console.clear_line()
