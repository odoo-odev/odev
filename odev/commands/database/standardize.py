from odev.common import progress
from odev.common.commands import OdoobinCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class StandardizeCommand(OdoobinCommand):
    """Remove customizations from a local Odoo database.
    Optionally also remove Studio customizations.
    """

    name = "standardize"
    aliases = ["std", "standard"]

    arguments = [
        {
            "name": "keep_studio",
            "aliases": ["--no-studio"],
            "action": "store_false",
            "help": "Remove Studio customizations.",
        },
    ]

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # No need for odoo-bin arguments as we're not calling it directly
        cls.remove_argument("odoo_args")

    def run(self):
        message: str = f"customizations from database {self.database.name!r}"

        with progress.spinner(f"Removing {message}"):
            self.odoobin.standardize(remove_studio=not self.args.keep_studio)

        logger.info(f"Removed {message}")
