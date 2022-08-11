from datetime import datetime

from odev.utils import logging
from odev.utils.config import ConfigManager


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    _logger.info("Migrating saved databases 'last_run' date in config files")

    with ConfigManager("databases") as dbs_config:
        for db_section in dbs_config.values():
            readable_date = db_section.pop("lastrun", None)
            if not readable_date:
                continue
            try:
                db_section["last_run"] = datetime.strptime(readable_date, "%a %d %B %Y, %H:%M:%S").isoformat()
            except ValueError:
                continue  # ignore invalid dates, last_run is removed from cfg, will repopulate at next odev run
