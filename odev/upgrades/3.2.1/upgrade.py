from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    config = ConfigManager("odev")
    old_psbe_upgrade_path = config.get("paths", "psbe_upgrade_repo_path")
    if old_psbe_upgrade_path:
        _logger.info("Migrating old psbe-custom-upgrade repo path")
        config.delete("paths", "psbe_upgrade_repo_path")
        config.set("paths", "custom_util_repo_path", old_psbe_upgrade_path)
