from odev.common import args, progress
from odev.common.commands import OdoobinCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class StandardizeCommand(OdoobinCommand):
    """Remove customizations from a local Odoo database.
    Optionally also remove Studio customizations.
    """

    _name = "standardize"
    _aliases = ["std", "standard"]

    keep_studio = args.Flag(aliases=["--no-studio"], default=True, description="Remove Studio customizations.")

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)

        # No need for odoo-bin arguments as we're not calling it directly
        cls.remove_argument("odoo_args")

    def run(self) -> None:
        if not self._database.exists or not self._database.is_odoo:
            raise self.error(f"Invalid database {self._database.name!r}, must be an Odoo database")

        message: str = f"customizations from database {self._database.name!r}"

        with progress.spinner(f"Removing {message}"):
            assert self.odoobin is not None
            self.odoobin.standardize(remove_studio=not self.args.keep_studio)

        logger.info(f"Removed {message}")
