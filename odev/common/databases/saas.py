"""Odoo Online (SaaS) database class."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from odev.common import string
from odev.common.connectors import SaasConnector
from odev.common.databases import Database, Filestore
from odev.common.errors import ConnectorError
from odev.common.mixins import SaasConnectorMixin
from odev.common.version import OdooVersion


ODOO_DOMAIN_SUFFIX = ".odoo.com"


class SaasDatabase(SaasConnectorMixin, Database):
    """Odoo Online (SaaS) database class."""

    connector: SaasConnector

    _url: str = None
    """The URL of the SaaS database."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    _platform: str = "saas"
    _platform_display: str = "Odoo Online (SaaS)"

    def __init__(self, name: str):
        """Initialize the Odoo SaaS database and infer its name or URL."""
        super().__init__(name)
        parsed = urlparse(name)

        if not parsed.scheme and ODOO_DOMAIN_SUFFIX in name:
            parsed = urlparse(f"https://{name}")

        if parsed.netloc:
            if not parsed.netloc.endswith(ODOO_DOMAIN_SUFFIX):
                raise ConnectorError(f"Invalid SaaS database name or URL {name!r}", None)

            self._name: str = parsed.netloc.removesuffix(ODOO_DOMAIN_SUFFIX)
            self._url: str = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self._name = name.removesuffix(ODOO_DOMAIN_SUFFIX)
            self._url = f"https://{name}{ODOO_DOMAIN_SUFFIX}"

        self.saas = self._saas(self.url)
        """The SaaS connector for this database."""

    def __enter__(self):
        self.connector = self.saas.__enter__()
        return self

    def __exit__(self, *args):
        self.saas.__exit__(*args)

    @property
    def url(self) -> str:
        """Return the URL of the database."""
        return self._url

    @property
    def exists(self) -> bool:
        return self.saas.exists

    @property
    def is_odoo(self) -> bool:
        return self.exists

    @property
    def version(self) -> Optional[OdooVersion]:
        version = self.saas.database_info().get("base_version")

        if version is None:
            return None

        return OdooVersion(version)

    @property
    def edition(self) -> Optional[str]:
        return "enterprise"

    @property
    def filestore(self) -> Filestore:
        if self._filestore is None:
            self._filestore = Filestore(
                path=None,
                size=string.bytes_from_string(self.saas.database_info().get("size_filestore", "0")),
            )

        return self._filestore

    @property
    def size(self) -> int:
        return string.bytes_from_string(self.saas.database_info().get("size_backup", "0"))

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
    def rpc_port(self) -> Optional[int]:
        return 443

    def dump(self, filestore: bool = False, path: Path = None) -> Optional[Path]:
        if path is None:
            path = self.odev.dumps_path

        path.mkdir(parents=True, exist_ok=True)
        filename = self._get_dump_filename(
            filestore,
            suffix=self.platform.name,
            extension="dump" if not filestore else None,
        )
        file = path / filename

        if file.exists() and not self.console.confirm(f"File {file} already exists. Overwrite it?"):
            return None

        file.unlink(missing_ok=True)
        self.saas.dump(file, filestore)
        return file
