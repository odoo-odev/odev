from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    _logger.info("Resetting saved databases 'last_run' date in config files")

    dbs_config = ConfigManager("databases")
    for db_section in dbs_config.values():
        if db_section.pop("last_run", None):
            db_section["last_run"] = ""
