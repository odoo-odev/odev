"""Upgrade to odev 4.0.3"""

from odev.common.connectors import PostgresConnector
from odev.common.logging import logging
from odev.common.mixins import ListLocalDatabasesMixin
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:

    # --- Upgrade old database ---------------------------------------------------

    database_connector = ListLocalDatabasesMixin()

    with PostgresConnector("postgres") as my_db:
        for database in database_connector.list_databases():
            logger.debug(f"Updating collation version of database {database}")
            my_db.query(f"""ALTER DATABASE "{database}" REFRESH COLLATION VERSION""")
