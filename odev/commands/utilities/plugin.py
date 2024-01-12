"""Enable and disable plugins to add new features and commands."""

import re

from odev.common.commands import Command
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PluginCommand(Command):
    """Enable and disable plugins to add new features and commands."""

    name = "plugin"
    aliases = ["addons"]

    arguments = [
        {
            "name": "plugin",
            "help": """Plugin to enable or disable, must be a git repository hosted on GitHub.
            Use format <organization>/<repository>.
            """,
        },
        {
            "name": "--enable",
            "dest": "enable",
            "help": "Enable the given plugin.",
            "action": "store_true",
        },
        {
            "name": "--disable",
            "dest": "disable",
            "help": "Disable the given plugin.",
            "action": "store_true",
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.args.enable and self.args.disable:
            raise self.error(
                "Cannot enable and disable a plugin at the same time, remove one of `--enable` or `--disable` "
                "and try again"
            )

        if not self.args.enable and not self.args.disable:
            raise self.error("Must enable or disable a plugin, provide one of `--enable` or `--disable` and try again")

    def run(self):
        """Enable or disable a plugin."""
        repository = self.__parse_repository()

        if self.args.enable and repository not in self.config.plugins.enabled:
            with self.console.status(f"Enabling plugin {repository!r}"):
                self.config.plugins.enabled = [
                    plugin for plugin in self.config.plugins.enabled + [repository] if plugin
                ]
                logger.info(f"Enabled plugin {repository!r}")

        if self.args.disable and repository in self.config.plugins.enabled:
            with self.console.status(f"Disabling plugin {repository!r}"):
                self.config.plugins.enabled = [plugin for plugin in self.config.plugins.enabled if plugin != repository]
                self.odev.plugins_path.joinpath(repository.split("/", 1)[-1]).unlink()
                logger.info(f"Disabled plugin {repository!r}")

        self.odev.load_plugins()

    def __parse_repository(self) -> str:
        """Parse the repository name from the given plugin."""
        match = re.search(r"(?P<organization>[^/]+)/(?P<repository>[^/]+)$", self.args.plugin)

        if not match:
            raise self.error(f"Invalid plugin {self.args.plugin!r}, must be in format <organization>/<repository>")

        return "/".join([match.group("organization"), match.group("repository")])
