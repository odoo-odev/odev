"""Enable and disable plugins to add new features and commands."""

from odev.common import args
from odev.common.commands import Command
from odev.common.connectors import GitConnector
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PluginCommand(Command):
    """Enable and disable plugins to add new features and commands."""

    _name = "plugin"
    _aliases = ["addons"]
    _exclusive_arguments = [("enable", "disable")]

    enable = args.Flag(aliases=["--enable"], description="Download and enable an inactive plugin.")
    disable = args.Flag(aliases=["--disable"], description="Disable an active plugin.")
    plugin = args.String(
        description="""Plugin to enable or disable, must be a git repository hosted on GitHub.
        Use format <organization>/<repository>.
        """,
    )

    def run(self):
        """Enable or disable a plugin."""
        repository = GitConnector(self.args.plugin).name

        if self.args.enable:
            self.__add_plugin_to_config(repository)

            try:
                self.odev.load_plugins()
            except Exception as error:
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
            except Exception as error:
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
