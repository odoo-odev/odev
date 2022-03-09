"""Make a local Odoo database suitable for development."""
import os
from argparse import Namespace

from packaging.version import Version

from odev.constants.config import ODEV_CONFIG_DIR
from odev.exceptions import InvalidQuery
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class CleanCommand(commands.LocalDatabaseCommand):
    """
    Render a local Odoo database suitable for development:
      - Disable automated and scheduled actions
      - Disable mails
      - Set credentials for Administrator user to admin:admin
      - Set password for the first 50 users to odoo
      - Extend database validity to December 2050 and remove enterprise code
      - Set report.url and web.base.url to http://localhost:8069
      - Disable Oauth providers
      - Remove saas_% module and views
    """

    name = "clean"
    aliases = ["cl"]
    queries = [
        """
        UPDATE res_users SET login='admin',password='admin'
        WHERE id IN (SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 1)
        """,
        """
        UPDATE res_users SET password='odoo'
        WHERE login != 'admin' AND password IS NOT NULL AND id IN (
            SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 50
        )
        """,
        """
        DO $$ BEGIN IF (EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'res_users' AND column_name='totp_secret'
            ))
            THEN UPDATE res_users SET totp_secret = NULL AND id IN (
                SELECT id FROM res_users WHERE active='True' ORDER BY id ASC LIMIT 51
            );
        END IF; END; $$
        """,
        "DELETE FROM ir_config_parameter where key ='database.enterprise_code'",
        "DELETE FROM ir_config_parameter WHERE key='report.url'",
        "UPDATE ir_config_parameter SET value='http://localhost:8069' WHERE key='web.base.url'",
        "UPDATE ir_cron SET active='False'",
        "DELETE FROM fetchmail_server",
        "DELETE FROM ir_mail_server",
        "DO $$ BEGIN IF (EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES  WHERE TABLE_NAME = 'auth_oauth_provider')) "
        "THEN UPDATE auth_oauth_provider SET enabled = false; END IF; END; $$",
        "DELETE FROM ir_config_parameter WHERE key IN ('ocn.ocn_push_notification','odoo_ocn.project_id', 'ocn.uuid')",
        "UPDATE ir_module_module SET state='uninstalled' WHERE name ilike '%saas%'",
        "DELETE FROM ir_ui_view WHERE name ilike '%saas%'",
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        expiration_date = "2050-12-12"

        # The database expiration date became a datetime object in version 15.0,
        # as opposed to a date object in previous versions
        if self.db_version_parsed() >= Version("15.0"):
            expiration_date += " 00:00:00"

        self.queries.append(
            f"UPDATE ir_config_parameter SET value='{expiration_date}' WHERE key='database.expiration_date'",
        )

    def run(self):
        """
        Cleans a database and make it suitable for development and testing locally.
        """

        self.ensure_stopped()

        queries_file = os.path.join(ODEV_CONFIG_DIR, "clean_queries.sql")

        try:
            with open(queries_file, "r") as clean_queries:
                for query in [q.strip() for q in clean_queries.read().split(";") if q.strip()]:
                    _logger.debug(f"Query added to the list : {query}")
                    self.queries.append(query)
        except FileNotFoundError:
            pass

        _logger.info(f"Cleaning database {self.database}")
        result = self.run_queries(self.queries)

        if not result:
            raise InvalidQuery(f"An error occurred while cleaning up database {self.database}")

        self.config["databases"].set(self.database, "clean", True)

        _logger.info("Login to the administrator account with the credentials 'admin:admin'")
        _logger.info("Login to the first 50 users with their email address and the password 'odoo'")

        return 0
