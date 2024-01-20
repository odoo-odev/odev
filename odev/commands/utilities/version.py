from odev._version import __version__
from odev.common.commands import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class VersionCommand(Command):
    """Prints the current version of the application."""

    name = "version"
    aliases = ["v"]

    def run(self):
        """Prints the current version of the application."""
        logger.info(f"{self.odev.name.capitalize()} version [repr.version]{__version__}[/repr.version]")
