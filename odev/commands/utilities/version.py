from odev._version import __version__
from odev.common import string
from odev.common.commands import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class VersionCommand(Command):
    """Print the current version of odev and exit."""

    _name = "version"
    _aliases = ["v"]

    def run(self):
        """Prints the current version of the application."""
        logger.info(
            f"{self.odev.name.capitalize()} version {string.stylize(self.odev.config.update.version, 'repr.version')}"
        )

        if self.odev.config.update.version != __version__:
            logger.warning(f"A newer version is available, consider running '{self.odev.name} update'")
