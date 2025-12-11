from odev._version import __version__
from odev.common import args, string
from odev.common.commands import Command
from odev.common.connectors.git import GitConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class VersionCommand(Command):
    """Print the current version of odev and exit."""

    _name = "version"
    _aliases = ["v"]

    show_plugins = args.Flag(aliases=["-p", "--show-plugins"], help="Show plugins versions")

    def run(self):
        """Print the current version of the application."""
        name = self.odev.name.capitalize()
        version = string.stylize(self.odev.config.update.version, "repr.version")
        channel = string.stylize(f"({self.odev.release})", "color.black")
        logger.info(f"{name} version {version} {channel}")

        if self.odev.config.update.version != __version__:
            logger.warning(f"A newer version is available, consider running '{self.odev.name} update'")

        if self.show_plugins:
            plugins_list: list[str] = []

            for plugin in sorted(self.odev.plugins, key=lambda plugin: plugin.name):
                plugin_version = string.stylize(plugin.manifest["version"], "repr.version")
                plugin_repo = GitConnector(plugin.name)
                plugin_branch = string.stylize(
                    f"({plugin_repo.repository.active_branch.name if plugin_repo.repository else '<unknown>'})",
                    "color.black",
                )
                plugins_list.append(f"{plugin.name!r} version {plugin_version} {plugin_branch}")

            logger.info(f"Plugins:\n{string.join_bullet(plugins_list)}")
            self.console.print()
