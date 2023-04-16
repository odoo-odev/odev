from datetime import datetime

from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    _logger.info("Add the new configurable option 'min_delay_before_drop' with 10 days by default")
    config = ConfigManager("odev")
    config.set("cleaning", "min_delay_before_drop", "10")
    config.save()

    _logger.info("Creating a 'create_date' date in the databases config files for the auto clean feature")

    dbs_config = ConfigManager("databases")
    for db_section in dbs_config.values():
        readable_date = db_section.pop("lastrun", None)

        db_section["create_date"] = readable_date if readable_date else datetime.now().isoformat()
