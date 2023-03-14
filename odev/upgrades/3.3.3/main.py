import psycopg2

from odev.utils import logging
from odev.utils.config import ConfigManager
from odev.utils.psql import PSQL


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    _logger.info("Setting cleaned databases `database.is_neutralized` = true in `ir_config_parameter`")

    clean_databases = set()
    non_clean_databases = set()
    with ConfigManager("databases") as dbs_config:
        for database, db_section in dbs_config.items():
            clean = db_section.get("clean")

            psql = PSQL(database)
            try:
                psql.connect()
            except psycopg2.OperationalError as e:
                _logger.warning(f"Failing to connect to database {database}: {e}")
                continue

            try:
                if not clean:
                    has_enterprise_code = psql.query(
                        "SELECT TRUE FROM ir_config_parameter WHERE key = 'database.enterprise_code';"
                    )
                    clean = not has_enterprise_code

                if not clean:
                    has_cleaned_users = psql.query("SELECT TRUE FROM res_users WHERE password IN ('odoo', 'admin');")
                    clean = bool(has_cleaned_users)

                if clean:
                    psql.query(
                        """
                        INSERT INTO ir_config_parameter (key, value)
                        VALUES ('database.is_neutralized', true)
                            ON CONFLICT (key) DO UPDATE SET value = true;
                        """
                    )
                    clean_databases.add(database)
                else:
                    non_clean_databases.add(database)

            finally:
                psql.disconnect()

    _logger.info(f"Cleaned databases marked as neutralized: {clean_databases}")
    _logger.info(f"Non-cleaned databases: {non_clean_databases}")
