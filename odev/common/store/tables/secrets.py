from base64 import b64decode, b64encode
from dataclasses import dataclass
from io import StringIO
from typing import Literal, Optional, Sequence, Union

from agentcrypt.io import Container

from odev.common import prompt
from odev.common.logging import logging
from odev.common.postgres import PostgresTable


logger = logging.getLogger(__name__)


class NamedStringIO(StringIO):
    """StringIO with a name attribute."""

    name: str = "NamedStringIO"


@dataclass
class Secret:
    """Simple representation of a secret."""

    key: str
    """Key (identifier) of the secret."""

    login: str
    """Login."""

    password: str
    """Password.
    WARNING: This is the plaintext password, be careful with what you display.
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.key!r})"


class SecretStore(PostgresTable):
    """A class for managing credentials in a vault database."""

    name = "secrets"
    """Name of the table in which the secrets are stored."""

    _columns = {
        "name": "VARCHAR PRIMARY KEY",
        "login": "VARCHAR",
        "cypher": "TEXT",
    }

    def get(
        self,
        key: str,
        fields: Sequence[Union[Literal["login"], Literal["password"]]] = None,
        prompt_format: str = None,
    ) -> Secret:
        """Get a secret from the vault.

        :param name: The key for the secret.
        :param fields: The fields to get. If not provided, both login and password will be returned.
        :param prompt_format: A ready-to-format string to display when asking for the fields.
        Possible dynamic values are:
            - {key}: The key for the secret.
            - {field}: The field to get.

        Default: "{field} for '{key}':"
        :return: The login and password.
        :rtype: Tuple[str, str]
        """
        secret = self._get(key)

        if secret is None:
            logger.debug(f"Secret {key!r} not found in vault {self!r}")

            if fields is None:
                fields = ("login", "password")

            if prompt_format is None:
                prompt_format = "{field} for '{key}':".capitalize()

            secret = Secret(
                key,
                "login" in fields and prompt.text(prompt_format.format(key=key, field="login")) or "",
                "password" in fields and prompt.secret(prompt_format.format(key=key, field="password")) or "",
            )
            self._set(secret)

        return secret

    def invalidate(self, key: str):
        """Invalidate a secret in the vault.

        :param key: The key for the secret.
        """
        self._delete(key)
        logger.debug(f"Secret {key!r} invalidated and removed from {self.name!r}")

    def _get(self, name: str) -> Optional[Secret]:
        """Get a secret from the vault.

        :param name: The name of the secret.
        :return: The login and password.
        :rtype: Tuple[str, str]
        """
        with self:
            result = self.query(
                f"""
                SELECT login, cypher
                FROM {self.name}
                WHERE name = '{name.lower()}'
                LIMIT 1
                """
            )

        if not result:
            return None

        return Secret(name, result[0][0], SecretStore.decrypt(result[0][1]))

    def _set(self, secret: Secret):
        """Save a secret to the vault.

        :param name: The name of the secret.
        :param login: The login.
        :param password: The password.
        """
        cypher = SecretStore.encrypt(secret.password)

        with self:
            self.query(
                f"""
                INSERT INTO {self.name} (name, login, cypher)
                VALUES ('{secret.key.lower()}', '{secret.login}', '{cypher}')
                ON CONFLICT (name) DO
                    UPDATE SET login = '{secret.login}', cypher = '{cypher}'
                """
            )

    def _delete(self, name: str):
        """Remove a secret from the vault.

        :param key: The key for the secret.
        """
        with self:
            self.query(
                f"""
                DELETE FROM {self.name}
                WHERE name = '{name.lower()}'
                """
            )

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Symmetrically encrypt a string using ssh-agent.

        :param plaintext: The string to encrypt.
        :return: The encrypted string.
        :rtype: str
        """

        with NamedStringIO() as stream, Container.create(stream) as container:
            container.write(plaintext)
            container.flush()
            encrypted = stream.getvalue()
        return b64encode(encrypted.encode()).decode()

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Symmetrically decrypt a string using ssh-agent.

        :param ciphertext: The string to decrypt.
        :return: The decrypted string.
        :rtype: str
        """

        decoded = b64decode(ciphertext.encode()).decode()

        with NamedStringIO(decoded) as stream, Container.load(stream) as container:
            return container.getvalue().decode()
