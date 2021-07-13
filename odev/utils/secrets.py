import base64
import configparser
import logging
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Iterator, Optional

from agentcrypt.exceptions import AgentCryptException
from agentcrypt.io import Container


__all__ = [
    "ssh_agent_encrypt",
    "ssh_agent_decrypt",
    "StoreSecret",
    "secret_storage",
]


_logger: logging.Logger = logging.getLogger(__name__)


class NamedStringIO(StringIO):
    """StringIO with `name` attribute"""

    name: str = "StringIO"


def ssh_agent_encrypt(message: str) -> str:
    """
    Encrypt a string with symmetric encryption using ssh-agent.

    :param message: the string to encrypt.
    :return: the encrypted message, base64-encoded
    """
    with NamedStringIO() as s, Container.create(s) as cntr:
        cntr.write(message)
        cntr.flush()
        encrypted: str = s.getvalue()
    return base64.b64encode(encrypted.encode()).decode()


def ssh_agent_decrypt(encrypted: str) -> str:
    """
    Decrypt a string previously encrypted with `ssh_agent_encrypt` using ssh-agent.

    :param encrypted: the encrypted message, base64-encoded
    :return: the original decrypted message.
    """
    decoded: str = base64.b64decode(encrypted.encode()).decode()
    with NamedStringIO(decoded) as s, Container.load(s) as cntr:
        return cntr.getvalue().decode()


class StoreSecret(Exception):
    """Signal exception that indicates the secret should be stored."""

    def __init__(self, secret: str):
        super().__init__()
        self.secret: str = secret


@contextmanager
def secret_storage(name: str) -> Iterator[Optional[str]]:
    # TODO: DRY
    odev_config_path: str = "%s/.config/odev/odev.cfg" % (str(Path.home()))
    config = configparser.ConfigParser()
    config.read(odev_config_path)

    secret: Optional[str] = None
    if "secrets" in config:
        github_token_encrypted = config["secrets"].get(name)
        if github_token_encrypted is not None:
            try:
                secret = ssh_agent_decrypt(github_token_encrypted)
            except AgentCryptException:
                _logger.warning(
                    f'Failed decrypting stored "{name}" secret. '
                    f"Is ssh-agent running?"
                )
                # TODO: keys changed check? option to delete secrets?

    try:
        yield secret

    except StoreSecret as store:
        secret = store.secret
        try:
            github_token_encrypted = ssh_agent_encrypt(secret)
        except AgentCryptException:
            _logger.warning(f'Failed encrypting "{name}" secret. Is ssh-agent running?')
        else:
            if "secrets" not in config:
                config.add_section("secrets")
            config.set("secrets", name, github_token_encrypted)
            with open(odev_config_path, "w") as fp:
                config.write(fp)
