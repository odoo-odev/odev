"""Upgrade to odev 4.0.0"""

from odev.common.config import Config
from odev.common.connectors import PostgresConnector
from odev.common.logging import logging
from odev.common.mixins import ListLocalDatabasesMixin


logger = logging.getLogger(__name__)


def run(config: Config) -> None:

    # --- Upgrade old database ---------------------------------------------------

    database_connector = ListLocalDatabasesMixin()

    with PostgresConnector("postgres") as my_db:
        for database in database_connector.list_databases():
            logger.debug(f"Updating collation version of database {database}")
            my_db.query(f"""ALTER DATABASE "{database}" REFRESH COLLATION VERSION""")
