"""Upgrade to odev 4.32.0.

Migrate the list of enabled plugins out of the configuration and into the plugins directory.

Plugins used to be recorded twice: as a link under the plugins directory, and as an entry in the 'plugins.enabled'
configuration option. The two could disagree, which is what the 'missing' and 'shadowed' states of `odev plugin
--list` used to report. The link is now the only record, so this materializes a link for every plugin that was
enabled but not linked, then drops the configuration option for good.
"""

from pathlib import Path

from odev.common import progress
from odev.common.logging import logging
from odev.common.odev import Odev
from odev.common.plugins import plugin_identity, plugin_module_name


logger = logging.getLogger(__name__)

CONFIG_SECTION = "plugins"
CONFIG_OPTION = "enabled"


def run(odev: Odev) -> None:
    enabled = _enabled_plugins(odev)

    if enabled:
        with progress.spinner("Migrating enabled plugins to the plugins directory"):
            odev.plugins_path.mkdir(parents=True, exist_ok=True)

            for plugin in enabled:
                _link_plugin(odev, plugin)

    if CONFIG_SECTION in odev.config.parser.sections():
        odev.config.delete(CONFIG_SECTION)

    odev._forget_plugins()


def _enabled_plugins(odev: Odev) -> list[str]:
    """Read the plugins that were enabled in the configuration, before the option is removed.

    :param odev: The framework instance
    :return: Names of the plugins, in the format `organization/repository`
    """
    value = odev.config.parser.get(CONFIG_SECTION, CONFIG_OPTION, fallback="") or ""
    return [plugin for plugin in value.split(",") if plugin]


def _link_plugin(odev: Odev, plugin: str) -> None:
    """Create the link recording a plugin as installed, unless it is already there.

    :param odev: The framework instance
    :param plugin: Name of the plugin, in the format `organization/repository`
    """
    plugin_path: Path = odev.plugins_path / plugin_module_name(plugin)
    repository_path: Path = odev.config.paths.repositories / plugin

    if plugin_path.is_symlink() or plugin_path.is_dir():
        linked = plugin_identity(plugin_path.resolve())

        if linked != plugin:
            logger.warning(
                f"Plugin {plugin!r} was enabled but the module name {plugin_path.name!r} is used by {linked!r}, "
                f"so it could never be loaded; it is now uninstalled"
            )

        return

    if not repository_path.is_dir():
        logger.warning(
            f"Plugin {plugin!r} was enabled but its repository is missing from "
            f"{repository_path.as_posix()}; it is now uninstalled, run "
            f"'odev plugin --enable {plugin}' to install it again"
        )
        return

    logger.debug(f"Linking plugin {plugin!r} to {repository_path.as_posix()}")
    plugin_path.symlink_to(repository_path, target_is_directory=True)
