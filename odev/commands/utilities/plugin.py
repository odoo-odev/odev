"""Enable and disable plugins to add new features and commands."""

from typing import cast

from odev.common import args, string
from odev.common.commands import Command
from odev.common.connectors import GitConnector
from odev.common.logging import logging
from odev.common.odev import Plugin


logger = logging.getLogger(__name__)


class PluginCommand(Command):
    """Enable and disable plugins to add new features and commands."""

    _name = "plugin"
    _exclusive_arguments = [("enable", "disable", "show")]

    enable = args.Flag(aliases=["-e", "--enable"], description="Download and enable an inactive plugin.")
    disable = args.Flag(aliases=["-d", "--disable"], description="Disable an active plugin.")
    show = args.Flag(
        aliases=["-s", "--show"],
        description="Show the state of a plugin and its description if available.",
    )
    plugin = args.String(
        description="""Plugin to enable or disable, must be a git repository hosted on GitHub.
        Use format <organization>/<repository>.
        """,
    )

    def run(self):
        """Enable or disable a plugin."""
        plugin_name = GitConnector(self.args.plugin).name

        if self.args.enable:
            self.__add_plugin_to_config(plugin_name)

            try:
                self.odev.load_plugins()
                plugin = self.__get_plugin(plugin_name)
                dependencies = plugin.manifest["depends"]

                for dependency in dependencies:
                    self.__add_plugin_to_config(dependency)

                self.odev.load_plugins()
                logger.info(
                    f"Enabled plugin {plugin.name!r}"
                    + (f" and {len(dependencies)} dependencies" if dependencies else "")
                )
            except Exception as error:
                self.__remove_plugin_from_config(plugin_name)
                raise error

        elif self.args.disable:
            self.__remove_plugin_from_config(plugin_name)
            plugin = self.__get_plugin(plugin_name)

            try:
                if plugin.path is not None:
                    plugin.path.unlink(missing_ok=True)

                self.odev.load_plugins()
                logger.info(f"Disabled plugin {plugin_name!r}")
            except Exception as error:
                self.__add_plugin_to_config(plugin_name)
                raise error

        else:
            if plugin_name not in self.config.plugins.enabled:
                logger.info(f"Plugin {plugin_name!r} is {string.stylize('disabled', 'color.red')}")
            else:
                plugin = self.__get_plugin(plugin_name)
                logger.info(
                    string.normalize_indent(
                        f"""Plugin {plugin.name!r} is {string.stylize('enabled', 'color.green')}
                        {string.stylize('Version:', 'color.black')} {string.stylize(plugin.manifest['version'], 'repr.version')}
                        {string.stylize('Path:', 'color.black')}    {plugin.path.resolve()}
                        """
                    )
                )

                if plugin.manifest["description"]:
                    self.console.print()
                    self.console.print(string.indent(cast(str, plugin.manifest["description"]), 4))

    def __add_plugin_to_config(self, repository: str):
        """Add the given plugin to the config."""
        if repository in self.config.plugins.enabled:
            raise self.error(f"Plugin {repository!r} is already enabled")

        plugins = [*self.config.plugins.enabled, repository]
        self.config.plugins.enabled = [plugin for plugin in plugins if plugin]

    def __remove_plugin_from_config(self, repository: str):
        """Remove the given plugin from the config."""
        if repository not in self.config.plugins.enabled:
            raise self.error(f"Plugin {repository!r} is not enabled")

        self.config.plugins.enabled = [plugin for plugin in self.config.plugins.enabled if plugin != repository]

    def __get_plugin(self, name: str) -> Plugin:
        """Find a plugin by its name."""
        plugin = next((plugin for plugin in self.odev.plugins if plugin[0] == name), None)

        if plugin is None:
            raise self.error(f"Plugin {name!r} not found or could not be loaded")

        return plugin
