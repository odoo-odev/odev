"""Odoo Online (SaaS) database class."""

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from odev.common import string
from odev.common.connectors import SaasConnector
from odev.common.databases import Database
from odev.common.mixins import SaasConnectorMixin
from odev.common.version import OdooVersion


ODOO_DOMAIN_SUFFIX = ".odoo.com"


class SaasDatabase(SaasConnectorMixin, Database):
    """Odoo Online (SaaS) database class."""

    connector: SaasConnector

    url: str = None
    """The URL of the SaaS database."""

    _platform: str = "saas"

    def __init__(self, name: str):
        """Initialize the Odoo SaaS database and infer its name or URL."""
        super().__init__(name)
        parsed = urlparse(name)

        if parsed.netloc:
            if not parsed.netloc.endswith(ODOO_DOMAIN_SUFFIX):
                raise ValueError(f"Invalid SaaS database name or URL {name!r}")

            self.name: str = parsed.netloc.removesuffix(ODOO_DOMAIN_SUFFIX)
            self.url: str = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self.name = name.removesuffix(ODOO_DOMAIN_SUFFIX)
            self.url = f"https://{name}{ODOO_DOMAIN_SUFFIX}"

        self.saas = self._saas(self.url)
        """The SaaS connector for this database."""

    def __enter__(self):
        self.connector = self.saas.__enter__()
        return self

    def __exit__(self, *args):
        self.saas.__exit__(*args)

    def info(self):
        return {
            **super().info(),
            "is_odoo_running": self.is_odoo,
        }

    @property
    def exists(self) -> bool:
        return self.saas.exists

    @property
    def is_odoo(self) -> bool:
        return self.exists

    @property
    def odoo_url(self) -> str:
        return self.url

    @property
    def odoo_version(self) -> Optional[OdooVersion]:
        version = self.saas.database_info().get("base_version")

        if version is None:
            return None

        return OdooVersion(version)

    @property
    def odoo_edition(self) -> Optional[str]:
        return "enterprise"

    @property
    def odoo_filestore_path(self) -> Optional[Path]:
        return None

    @property
    def odoo_filestore_size(self) -> Optional[int]:
        return string.bytes_from_string(self.saas.database_info().get("size_filestore"))

    @property
    def size(self) -> int:
        return string.bytes_from_string(self.saas.database_info().get("size_backup"))

    @property
    def last_access_date(self) -> Optional[datetime]:
        return None

    @property
    def odoo_rpc_port(self) -> Optional[int]:
        return 443
