import logging
from abc import ABC, abstractmethod
from typing import MutableMapping, Optional, Tuple

from agentcrypt.exceptions import AgentCryptException

from odev.utils.config import ConfigManager
from odev.utils.logging import PromptFn
from odev.utils.secrets import ssh_agent_decrypt, ssh_agent_encrypt


__all__ = [
    "ValueCodec",
    "Passthrough",
    "SecretCodec",
    "CredentialsHelper",
]


_logger = logging.getLogger(__name__)


class ValueCodec(ABC):
    @abstractmethod
    def encode(self, decoded: Optional[str]) -> Optional[str]:
        ...

    @abstractmethod
    def decode(self, encoded: Optional[str]) -> Optional[str]:
        ...


class Passthrough(ValueCodec):
    def encode(self, decoded: Optional[str]) -> Optional[str]:
        return decoded

    def decode(self, encoded: Optional[str]) -> Optional[str]:
        return encoded


class SecretCodec(ValueCodec):
    def __init__(self, secret_name: Optional[str] = None):
        self.secret_name: Optional[str] = secret_name

    def encode(self, decoded: Optional[str]) -> Optional[str]:
        if decoded is None:
            return None
        try:
            return ssh_agent_encrypt(decoded)
        except AgentCryptException:
            secret_name: str = f' "{self.secret_name}"' if self.secret_name else ""
            _logger.warning(f"Failed encrypting{secret_name} secret. Is ssh-agent running?")
            return None  # TODO: check/handle consequences of this

    def decode(self, encoded: Optional[str]) -> Optional[str]:
        if encoded is None:
            return None
        try:
            return ssh_agent_decrypt(encoded)
        except AgentCryptException:
            secret_name: str = f' "{self.secret_name}"' if self.secret_name else ""
            _logger.warning(f"Failed decrypting{secret_name} secret. Is ssh-agent running?")
            return None


class CredentialsHelper:
    def __init__(self):
        self.config: ConfigManager = ConfigManager("credentials")
        self.values_to_store: MutableMapping[Tuple[str, str], Optional[str]] = {}

    def get(
        self,
        fullname: str,
        prompt: str,
        value: Optional[str] = None,
        prompt_fn: PromptFn = _logger.ask,  # type: ignore
        store_codec: Optional[ValueCodec] = None,
    ) -> Optional[str]:
        section: str
        name: str
        section, name = fullname.split(".")
        if store_codec is None:
            store_codec = Passthrough()
        # only check cfg and prompt if value wasn't provided directly (ie. cmdline),
        if value is None:
            value = store_codec.decode(self.config.get(section, name, None))
            if value is None:
                value = prompt_fn(prompt)
                self.values_to_store[(section, name)] = store_codec.encode(value)

        return value

    def secret(
        self,
        fullname: str,
        prompt: str,
        value: Optional[str] = None,
        prompt_fn: PromptFn = _logger.password,  # type: ignore
    ) -> Optional[str]:
        return self.get(
            fullname,
            prompt,
            value=value,
            prompt_fn=prompt_fn,
            store_codec=SecretCodec(fullname),
        )

    def store_pending(self) -> None:
        with self.config:
            for (section, name), value in self.values_to_store.items():
                if value is None:
                    continue
                self.config.set(section, name, value)

    def __enter__(self) -> "CredentialsHelper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not any((exc_type, exc_val, exc_tb)):
            self.store_pending()
