"""Odoo Online (SaaS) database class."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from odev.common import prompt, string
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

        if not parsed.scheme and ODOO_DOMAIN_SUFFIX in name:
            parsed = urlparse(f"https://{name}")

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
    def expiration_date(self) -> Optional[datetime]:
        return datetime.strptime(self.saas.database_info().get("date_expire"), "%Y-%m-%d %H-%M-%S UTC")

    @property
    def uuid(self) -> Optional[str]:
        return self.saas.database_info().get("uuid")

    @property
    def domains(self) -> List[str]:
        """Return the domain names of the database."""
        return self.saas.database_info().get("hostnames")

    @property
    def mode(self) -> str:
        """Return the mode of the database."""
        return self.saas.database_info().get("metabase_mode")

    @property
    def active(self) -> bool:
        """Return whether the database has been activated."""
        return self.saas.database_info().get("metabase_status") == "activated"

    @property
    def last_access_date(self) -> Optional[datetime]:
        return None

    @property
    def odoo_rpc_port(self) -> Optional[int]:
        return 443

    def info(self):
        return {
            **super().info(),
            "is_odoo_running": self.is_odoo,
            "mode": self.mode,
            "active": self.active,
            "domains": self.domains,
        }

    def dump(self, filestore: bool = False, path: Path = None) -> Optional[Path]:
        if path is None:
            path = self.odev.dumps_path

        path.mkdir(parents=True, exist_ok=True)
        filename = self._get_dump_filename(filestore, suffix=self.platform, extension="dump" if not filestore else None)
        file = path / filename

        if file.exists() and not prompt.confirm(f"File {file} already exists. Overwrite it?"):
            return None

        file.unlink(missing_ok=True)
        self.saas.dump(file, filestore)
        return file
