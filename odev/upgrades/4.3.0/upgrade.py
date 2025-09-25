"""Upgrade to odev 4.3.0.

Migrate existing secrets to the new table structure.

Before:
name      | login    | cipher
-------------------------------
url:scope | username | password

After:
id | name | scope | platform | login    | cipher
--------------------------------------------------
1  | url  | scope | platform | username | password
"""

from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


NAME_SPLIT_LENGTHS = {
    "local": 2,
    "remote": 3,
}


def run(odev: Odev) -> None:
    logger.warning(
        """This upgrade will bring modifications to the way passwords are stored in Odev, this will be mostly
        transparent to you but some session cookies might be removed during this operation; we'll do our best to keep
        important secrets such as your Odoo account, two-factor authentication tokens and database passwords
        """
    )

    odev.store.query("CREATE TABLE IF NOT EXISTS secrets_backup AS TABLE secrets")
    odev.store.query("DROP TABLE secrets")
    odev.store.query(
        """
        CREATE TABLE IF NOT EXISTS secrets (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL,
            scope VARCHAR,
            platform VARCHAR,
            login VARCHAR,
            cipher TEXT NOT NULL
        )
        """
    )

    secrets = odev.store.query("SELECT name, login, cipher FROM secrets_backup")

    for secret in secrets:
        name, login, cipher = secret

        if name == "odoo.com:pass":
            name, scope, platform = "accounts.odoo.com", "user", ""
        elif name.endswith((":pass", ":rpc")):
            scope = "user"
            split = name.split(":")

            if len(split) == NAME_SPLIT_LENGTHS["local"]:
                name, platform = split[0], "local"
            elif len(split) == NAME_SPLIT_LENGTHS["remote"]:
                name, platform = split[1], "remote"
        elif name.endswith((":session_id", ":td_id")):
            platform = ""
            name, scope = name.split(":")
        else:
            scope, platform = "", ""

        odev.store.query(
            f"""
            INSERT INTO secrets (name, scope, platform, login, cipher)
            VALUES ({name!r}, {scope!r}, {platform!r}, {login!r}, {cipher!r})
            """,
        )

    odev.store.query("DROP TABLE secrets_backup")
