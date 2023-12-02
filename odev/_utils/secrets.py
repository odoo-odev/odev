import base64
from io import StringIO

from agentcrypt.io import Container


__all__ = [
    "ssh_agent_encrypt",
    "ssh_agent_decrypt",
]


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
