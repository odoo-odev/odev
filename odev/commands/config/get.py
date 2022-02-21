from argparse import Namespace

from odev.exceptions.commands import InvalidArgument
from odev.structures import commands
from odev.utils import logging
from odev.utils.logging import term


_logger = logging.getLogger(__name__)


class GetCommand(commands.Command):
    """
    Get a config parameter as used within odev.
    """

    name = "get"
    aliases = ["get-config", "config", "conf"]
    arguments = [
        {
            "name": "key",
            "help": "Configuration key to fetch, in the format `<section>.<option>`",
            "nargs": "?",
            "default": "",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        split = self.args.key.split(".")

        if len(split) == 2:
            self.section, self.key = split
        elif len(split) > 2:
            raise InvalidArgument("Too many parts in key parameter")
        elif len(split) == 0:
            self.section = self.key = ""
        else:
            self.section = self.args.key
            self.key = ""

    def _format_section(self, section=None):
        section = section or self.section
        return term.darkolivegreen3_bold(f"\n[{section}]")

    def _format_key_value(self, key=None, value=None):
        key = key or self.key
        value = value or term.snow4_italic("No value")
        return key + term.snow4(" = ") + term.lightcoral(value)

    def run(self):
        """
        Read a value from a config key.
        """

        if not self.key:
            if not self.section:
                for section, vals in self.config["odev"].items():
                    print(self._format_section(section))

                    for key, val in vals.items():
                        print(self._format_key_value(key, val))

                return 0

            section = self.config["odev"][self.section]

            if not section:
                raise ValueError(f"Section {self.section} does not exist")

            print(self._format_section())

            for key, val in section.items():
                print(self._format_key_value(key, val))

            return 0

        value = self.config["odev"].get(self.section, self.key)
        print(self._format_section())
        print(self._format_key_value(value=value))
        return 0
