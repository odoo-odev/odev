from odev.utils import logging
from odev.utils.config import ConfigManager


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    _logger.info("Resetting saved databases 'last_run' date in config files")

    with ConfigManager("databases") as dbs_config:
        for db_section in dbs_config.values():
            if db_section.pop("last_run", None):
                db_section["last_run"] = ""
