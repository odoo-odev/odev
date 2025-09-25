"""Upgrade to odev 4.0.20.

Migrate stored password from agentcrypt to ssh-crypt
"""

from base64 import b64decode, b64encode
from io import StringIO

from ssh_crypt import encrypt as ssh_encrypt

from odev.common.errors import OdevError
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


class NamedStringIO(StringIO):
    """StringIO with a name attribute."""

    name: str = "NamedStringIO"


def run(odev: Odev) -> None:
    secrets = odev.store.query(
        """
        SELECT name, cipher
        FROM secrets
        """
    )

    try:
        from agentcrypt3.exceptions import NoContainerException  # noqa: PLC0415
        from agentcrypt3.io import Container  # noqa: PLC0415
    except ImportError:
        try:
            from agentcrypt.exceptions import NoContainerException  # noqa: PLC0415
            from agentcrypt.io import Container  # noqa: PLC0415
        except ImportError:
            logger.warning(
                f"""
                Cannot find module 'agentcrypt'
                {len(secrets)} stored secrets will be reinitialized as they cannot be migrated to
                the new encryption method using 'ssh-crypt' and will need to be re-entered later
                """
            )
            logger.info(
                """
                You can abort the update now and install 'agentcrypt3' (or 'agentcrypt') through pip,
                then run 'odev update' to try and migrate the existing secrets, or continue the update now
                and clear the stored secrets
                """
            )

            if odev.console.confirm("Abort the update now?"):
                raise OdevError("Update aborted") from None

            odev.store.secrets.clear()
            return

    logger.info(f"Migrating {len(secrets)} stored secrets to the new encryption method")

    for name, ciphertext in secrets:
        decoded = b64decode(ciphertext.encode()).decode()

        try:
            with NamedStringIO(decoded) as stream, Container.load(stream) as container:
                plaintext = container.getvalue().decode()
        except NoContainerException as error:
            logger.debug(f"Error decrypting secret '{name}': {error}")
            continue

        encoded_ciphertext = b64encode(ssh_encrypt(plaintext)).decode()
        odev.store.query(
            f"""
            UPDATE secrets
            SET cipher = '{encoded_ciphertext}'
            WHERE name = '{name}'
            """
        )
