import logging

from odev.utils.config import ConfigManager


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    with ConfigManager("odev") as config:
        old_psbe_upgrade_path = config.get("paths", "psbe_upgrade_repo_path")
        if old_psbe_upgrade_path:
            _logger.info("Migrating old psbe-custom-upgrade repo path")
            config.delete("paths", "psbe_upgrade_repo_path")
            config.set("paths", "custom_util_repo_path", old_psbe_upgrade_path)
