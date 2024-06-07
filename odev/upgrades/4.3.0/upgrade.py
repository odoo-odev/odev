"""Upgrade to odev 4.3.0

Migrate existing secrets to the new table structure.

Before:
id | name      | login    | cipher
------------------------------------
1  | url:scope | username | password

After:
id | name | scope | platform | login    | cipher
--------------------------------------------------
1  | url  | scope | platform | username | password
"""

from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:
    logger.warning(
        """This upgrade will bring modifications to the way passwords are stored in Odev, this will be mostly
        transparent to you but some session cookies might be removed during this operation; we'll do our best to keep
        important secrets such as your Odoo account, two-factor authentication tokens and database passwords
        """
    )

    secrets = odev.store.query(
        """
        SELECT id, name
        FROM secrets
        """,
    )

    for secret in secrets:
        _id, name = secret

        if name == "odoo.com:pass":
            name, scope, platform = "accounts.odoo.com", "user", ""
        elif name.endswith(":pass") or name.endswith(":rpc"):
            scope = "user"
            split = name.split(":")

            if len(split) == 2:
                name, platform = split[0], "local"
            elif len(split) == 3:
                name, platform = split[1], "remote"
        elif name.endswith(":session_id") or name.endswith(":td_id"):
            platform = ""
            name, scope = name.split(":")

        odev.store.query(
            f"""
            UPDATE secrets
            SET name = '{name}', scope = '{scope}', platform = '{platform}'
            WHERE id = {_id}
            """,
        )
