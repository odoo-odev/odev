from base64 import b64decode, b64encode
from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Tuple

from paramiko.agent import Agent as SSHAgent, AgentKey
from paramiko.ssh_exception import SSHException
from ssh_crypt import E as ssh_decrypt, encrypt as ssh_encrypt

from odev.common.console import console
from odev.common.errors import OdevError
from odev.common.logging import logging
from odev.common.postgres import PostgresTable


logger = logging.getLogger(__name__)


@dataclass
class Secret:
    """Simple representation of a secret."""

    key: str
    """Key (identifier) of the secret."""

    login: str
    """Login. Can be empty if only a secret is required (i.e. API key)."""

    password: str
    """Password.
    WARNING: This is the plaintext password, be careful with what you display.
    """

    scope: str
    """Scope of the secret, if any. Used to differentiate between different credentials used on the same application."""

    platform: str
    """Platform where the secret is used, if any. Used to differentiate credentials used
    on databases with a similar name hosted on different platforms.
    """

    def __repr__(self) -> str:
        """Return a string representation of the secret to avoid passwords being
        displayed in logs or tracebacks.
        """
        return f"{self.__class__.__name__}({self.key!r}, scope={self.scope!r}, platform={self.platform!r})"


class SecretStore(PostgresTable):
    """A class for managing credentials in a vault database."""

    name = "secrets"
    """Name of the table in which the secrets are stored."""

    _columns = {
        "id": "SERIAL PRIMARY KEY",
        "name": "VARCHAR NOT NULL",
        "scope": "VARCHAR",
        "platform": "VARCHAR",
        "login": "VARCHAR",
        "cipher": "TEXT NOT NULL",
    }
    _constraints = {"secrets_unique_name_login_scope_platform": "UNIQUE(name, login, scope, platform)"}

    @classmethod
    def _list_ssh_keys(cls) -> Tuple[AgentKey, ...]:
        """List all SSH keys available in the ssh-agent."""
        keys = SSHAgent().get_keys()

        if not keys:
            raise OdevError("No SSH keys found in ssh-agent, or ssh-agent is not running.")

        return keys

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Symmetrically encrypt a string using ssh-agent.
        :param plaintext: The string to encrypt.
        :return: The encrypted string.
        :rtype: str
        """
        ciphered: Optional[str] = None

        for key in cls._list_ssh_keys():
            try:
                ciphered = str(b64encode(ssh_encrypt(plaintext, ssh_key=key)).decode()) if plaintext else ""
            except SSHException as e:
                logger.debug(f"Failed to encrypt with key {key.name}: {e}")

        if ciphered is None:
            raise OdevError("Encryption failed, no key could be used for signing.")

        return ciphered

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Symmetrically decrypt a string using ssh-agent.
        :param ciphertext: The string to decrypt.
        :return: The decrypted string.
        :rtype: str
        """
        deciphered: Optional[str] = None

        for key in cls._list_ssh_keys():
            try:
                deciphered = (
                    str(ssh_decrypt(b64decode(ciphertext.encode()).decode(), ssh_key=key)) if ciphertext else ""
                )
            except SSHException as e:
                logger.debug(f"Failed to decrypt with key {key.name}: {e}")
            except UnicodeDecodeError as e:
                logger.debug(f"Failed to decode decrypted string with key {key.name}: {e}")
            except ValueError as e:
                logger.debug(f"Unexpected error when trying to handle SSH key {key.name}: {e}")

        if deciphered is None:
            raise OdevError("Decryption failed, no key could be used")

        return str(deciphered)

    def get(
        self,
        key: str,
        fields: Optional[Sequence[Literal["login", "password"]]] = None,
        scope: str = "",
        platform: str = "",
        prompt_format: Optional[str] = None,
        ask_missing: bool = True,
        force_ask: bool = False,
    ) -> Secret:
        """Get a secret from the vault.
        :param name: The key for the secret.
        :param fields: The fields to get. If not provided, both login and password will be returned.
        :param scope: The scope of the secret.
        :param platform: The platform where the secret is used.
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
        secret = self._get(key, scope, platform) or Secret(key, "", "", scope, platform)
        old_secret = Secret(key, secret.login, secret.password, scope, platform)

        if fields is None:
            fields = ("login", "password")

        for field in fields:
            if prompt_format is None:
                prompt_format = "{field} for '{key}':"

            prompt_label = prompt_format.format(key=key, field=field)
            prompt_label = prompt_label[0].upper() + prompt_label[1:]
            current_value = getattr(secret, field, "")

            if current_value and not force_ask:
                continue

            if not current_value:
                secret_str = ", ".join(
                    filter(bool, (f"scope: {scope}" if scope else "", f"platform: {platform}" if platform else ""))
                )
                secret_str = f"({secret_str})" if secret_str else ""

                if force_ask:
                    logger.debug(f"Re-asking field {field!r} for secret {key!r} {secret_str}")
                else:
                    logger.debug(f"Secret {key!r} has no {field!r} in vault {secret_str}")

                    if not ask_missing:
                        continue

            if field == "password":
                value = console.secret(prompt_label)
            else:
                with console.no_bypass_prompt():
                    value = console.text(prompt_label, default=current_value)

            setattr(secret, field, value)

        if secret.login != old_secret.login or secret.password != old_secret.password:
            self._set(secret)

        return secret

    def set(
        self,
        key: str,
        login: str,
        password: str,
        scope: str = "",
        platform: str = "",
    ) -> Secret:
        """Save a secret to the vault.
        :param key: The key for the secret.
        :param login: The login.
        :param password: The password.
        :param scope: The scope of the secret.
        :param platform: The platform where the secret is used.
        """
        secret = Secret(key, login, password, scope, platform)
        self._set(secret)
        return secret

    def invalidate(self, key: str, scope: str = "", platform: str = ""):
        """Invalidate a secret in the vault.
        :param key: The key for the secret.
        """
        self._delete(key, scope, platform)
        secret_str = ", ".join(
            filter(bool, (f"scope: {scope}" if scope else "", f"platform: {platform}" if platform else ""))
        )
        secret_str = f"({secret_str})" if secret_str else ""
        logger.debug(f"Secret {key!r} invalidated and removed from {self.name!r} {secret_str}")

    def _get(
        self,
        name: str,
        scope: str = "",
        platform: str = "",
    ) -> Optional[Secret]:
        """Get a secret from the vault.
        :param name: The name of the secret.
        :return: The login and password.
        :rtype: Tuple[str, str]
        """
        result = self.database.query(
            f"""
            SELECT login, cipher
            FROM {self.name}
            WHERE name = '{name.lower()}' AND scope = '{scope}' AND platform = '{platform}'
            LIMIT 1
            """,
            nocache=True,
        )

        if not result:
            return None

        return Secret(name, result[0][0], SecretStore.decrypt(result[0][1]), scope, platform)

    def _set(self, secret: Secret):
        """Save a secret to the vault.
        :param secret: The secret to save.
        """
        cipher = SecretStore.encrypt(secret.password)
        self.database.query(
            f"""
            INSERT INTO {self.name} (name, login, cipher, scope, platform)
            VALUES ('{secret.key.lower()}', '{secret.login}', '{cipher}', '{secret.scope}', '{secret.platform}')
            ON CONFLICT (name, login, scope, platform) DO
                UPDATE SET login = '{secret.login}', cipher = '{cipher}'
            """
        )

    def _delete(self, name: str, scope: str = "", platform: str = ""):
        """Remove a secret from the vault.
        :param key: The key for the secret.
        """
        self.database.query(
            f"""
            DELETE FROM {self.name}
            WHERE name = '{name.lower()}' AND scope = '{scope}' AND platform = '{platform}'
            """
        )
