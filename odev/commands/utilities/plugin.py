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
    _aliases = ["plugins"]
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
        If `--show` is used and no plugin is provided, show the state of all plugins.
        """,
        nargs="?",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.args.plugin and not self.args.show:
            raise self.error("Missing argument: plugin")

    def run(self):
        """Enable or disable a plugin."""
        if self.args.show:
            if self.args.plugin:
                self.__show_plugin_info(self.args.plugin.split("/")[-1])
                return

            for plugin in self.odev.plugins:
                self.__show_plugin_info(plugin.name)
                self.console.print()

        if self.args.enable:
            self.odev.install_plugin(self.args.plugin)
            return

        if self.args.disable:
            self.odev.uninstall_plugin(self.args.plugin)
            return

    def __show_plugin_info(self, plugin_name: str):
        """Show the plugin information.

        :param plugin_name: The name of the plugin to show information for.
        """
        if plugin_name not in self.config.plugins.enabled:
            logger.info(f"Plugin {plugin_name!r} is {string.stylize('disabled', 'color.red')}")
        else:
            plugin = self.__get_plugin(plugin_name)
            plugin_git = GitConnector(plugin_name)
            logger.info(
                string.normalize_indent(
                    f"""
                    Plugin {plugin.name!r} is {string.stylize("enabled", "color.green")}
                    {string.stylize("Version:", "color.black")} {string.stylize(plugin.manifest["version"], "repr.version")}
                    {string.stylize("Branch:", "color.black")}  {string.stylize(cast(str, plugin_git.branch), "color.cyan")}
                    {string.stylize("Path:", "color.black")}    {plugin.path.resolve()}
                    """
                )
            )

            if plugin.manifest["description"]:
                self.console.print()
                self.console.print(string.indent(cast(str, plugin.manifest["description"]), 4).rstrip("\n"))

    def __get_plugin(self, name: str) -> Plugin:
        """Find a plugin by its name."""
        plugin = next((plugin for plugin in self.odev.plugins if plugin[0] == name), None)

        if plugin is None:
            raise self.error(f"Plugin {name!r} not found or could not be loaded")

        return plugin
