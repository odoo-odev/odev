"""Enable and disable plugins to add new features and commands."""

from odev.common import args
from odev.common.commands import Command
from odev.common.connectors import GitConnector
from odev.common.errors import ConnectorError
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PluginCommand(Command):
    """Enable and disable plugins to add new features and commands."""

    name = "plugin"
    aliases = ["addons"]

    action = args.String(description="Action to perform, either 'enable' or 'disable'.", choices=["enable", "disable"])
    plugin = args.String(
        description="""Plugin to enable or disable, must be a git repository hosted on GitHub.
        Use format <organization>/<repository>.
        """,
    )

    def run(self):
        """Enable or disable a plugin."""
        repository = GitConnector(self.args.plugin).name

        if self.args.action == "enable":
            self.__add_plugin_to_config(repository)

            try:
                self.odev.load_plugins()
            except ConnectorError as error:
                self.__remove_plugin_from_config(repository)
                raise error
            else:
                logger.info(f"Enabled plugin {repository!r}")

        else:
            self.__remove_plugin_from_config(repository)

            try:
                plugin_name = repository.split("/", 1)[-1].replace("-", "_").replace(".git", "")
                self.odev.plugins_path.joinpath(plugin_name).unlink(missing_ok=True)
                self.odev.load_plugins()
            except ConnectorError as error:
                self.__add_plugin_to_config(repository)
                raise error
            else:
                logger.info(f"Disabled plugin {repository!r}")

    def __add_plugin_to_config(self, repository: str):
        """Add the given plugin to the config."""
        if repository in self.config.plugins.enabled:
            raise self.error(f"Plugin {repository!r} is already enabled")

        self.config.plugins.enabled = [plugin for plugin in self.config.plugins.enabled + [repository] if plugin]

    def __remove_plugin_from_config(self, repository: str):
        """Remove the given plugin from the config."""
        if repository not in self.config.plugins.enabled:
            raise self.error(f"Plugin {repository!r} is not enabled")

        self.config.plugins.enabled = [plugin for plugin in self.config.plugins.enabled if plugin != repository]
