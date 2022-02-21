from argparse import Namespace

from odev.exceptions.commands import CommandAborted, InvalidArgument
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class SetCommand(commands.Command):
    """
    Set a config parameter to use within odev.

    Valid key-value pairs are defined as follows:
      - logger.theme: Theme to use for Odev's logger (minimal|extended)
      - path.odoo:    Local path to where odoo files are stored
      - path.dump:    Local path to where dump files are stored when downloaded through Odev
      - path.dev:     Local path to where custom development repositories are located
    """

    name = "set"
    aliases = ["set-config"]
    arguments = [
        {
            "name": "key",
            "help": "Configuration key to edit, in the format `<section>.<option>`",
        },
        {
            "name": "value",
            "help": "Value to save to the configuration file",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        split = self.args.key.split(".")

        if len(split) < 2:
            raise InvalidArgument("Missing section or option key in key parameter")
        elif len(split) > 2:
            raise InvalidArgument("Too many parts in key parameter")

        if not self.args.value:
            raise InvalidArgument(f"Missing value for key `{self.args.key}`")

        self.section, self.key = split
        self.value = self.args.value

    def run(self):
        """
        Write a value to a config key.
        """

        previous = self.config["odev"].get(self.section, self.key)

        if previous != self.value:
            if previous:
                _logger.warning(
                    "You are about overwrite an existing value " f"for {self.args.key} ({previous} -> {self.value})"
                )

                if not _logger.confirm("Do you want to continue?"):
                    raise CommandAborted()

            self.config["odev"].set(self.section, self.key, self.value)

        return 0
