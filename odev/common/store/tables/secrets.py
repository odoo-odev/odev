from base64 import b64decode, b64encode
from dataclasses import dataclass
from io import StringIO
from typing import Literal, Optional, Sequence, Union

from agentcrypt.io import Container  # type: ignore [import]

from odev.common.console import console
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
        """Return a string representation of the secret to avoid passwords being
        displayed in logs or tracebacks.
        """
        return f"{self.__class__.__name__}({self.key!r})"


class SecretStore(PostgresTable):
    """A class for managing credentials in a vault database."""

    name = "secrets"
    """Name of the table in which the secrets are stored."""

    _columns = {
        "name": "VARCHAR PRIMARY KEY",
        "login": "VARCHAR",
        "cipher": "TEXT",
    }

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

    def get(
        self,
        key: str,
        fields: Sequence[Union[Literal["login"], Literal["password"]]] = None,
        prompt_format: str = None,
        ask_missing: bool = True,
        force_ask: bool = False,
    ) -> Secret:
        """Get a secret from the vault.

        :param name: The key for the secret.
        :param fields: The fields to get. If not provided, both login and password will be returned.
        :param prompt_format: A ready-to-format string to display when asking for the fields.
        Possible dynamic values are:
            - {key}: The key for the secret.
            - {field}: The field to get.

        Default: "{field} for '{key}':"
        :param ask_missing: Whether to prompt the user for the missing fields.
        :param force_ask: Whether to prompt the user for all fields, even if they are already set.
        :return: The login and password.
        :rtype: Tuple[str, str]
        """
        secret = self._get(key) or Secret(key, "", "")
        old_secret = Secret(key, secret.login, secret.password)

        if fields is None:
            fields = ("login", "password")

        for field in fields:
            if prompt_format is None:
                prompt_format = "{field} for '{key}':".capitalize()

            prompt_label = prompt_format.format(key=key, field=field)
            current_value = getattr(secret, field, "")

            if current_value and not force_ask:
                continue

            if not current_value:
                if force_ask:
                    logger.debug(f"Re-asking field {field!r} for secret {key!r}")
                else:
                    logger.debug(f"Secret {key!r} has no {field!r} in vault")

                    if not ask_missing:
                        continue

            if field == "password":
                value = console.secret(prompt_label)
            else:
                value = console.text(prompt_label, default=current_value)

            setattr(secret, field, value)

        if secret.login != old_secret.login or secret.password != old_secret.password:
            self._set(secret)

        return secret

    def set(self, key: str, login: str, password: str) -> Secret:
        """Save a secret to the vault.

        :param key: The key for the secret.
        :param login: The login.
        :param password: The password.
        """
        secret = Secret(key, login, password)
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
        result = self.database.query(
            f"""
            SELECT login, cipher
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
        cipher = SecretStore.encrypt(secret.password)
        self.database.query(
            f"""
            INSERT INTO {self.name} (name, login, cipher)
            VALUES ('{secret.key.lower()}', '{secret.login}', '{cipher}')
            ON CONFLICT (name) DO
                UPDATE SET login = '{secret.login}', cipher = '{cipher}'
            """
        )

    def _delete(self, name: str):
        """Remove a secret from the vault.

        :param key: The key for the secret.
        """
        self.database.query(
            f"""
            DELETE FROM {self.name}
            WHERE name = '{name.lower()}'
            """
        )
