from datetime import datetime
from typing import ClassVar, Literal, Optional, cast
from urllib.parse import urlparse

from odev.common.config import DATETIME_FORMAT
from odev.common.databases import Branch, Database, Filestore, Repository
from odev.common.version import OdooVersion


class RemoteDatabase(Database):
    """Interact with remote Odoo databases, mainly through RPC."""

    _platform: ClassVar[Literal["remote", "saas", "paas"]] = "remote"  # type: ignore [assignment]
    """The platform on which the database is running."""

    _platform_display: ClassVar[str] = "Remote"
    """The display name of the platform on which the database is running."""

    _url: str
    """The URL of the remote database."""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        parsed = urlparse(url)

        if not parsed.scheme:
            parsed = urlparse(f"https://{url}")

        if parsed.netloc:
            self._name = parsed.netloc.split(".")[0]
            self._url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self._name = url
            self._url = f"http://{url}"

    def __enter__(self):
        self.rpc.__enter__()
        return self

    def __exit__(self, *args):
        self.rpc.__exit__(*args)

    @property
    def is_odoo(self) -> bool:
        return bool(self.rpc["ir.module.module"].search_count([("name", "=", "base")]))

    @property
    def version(self) -> Optional[OdooVersion]:
        version = (
            self.rpc["ir.module.module"]
            .search_read(
                [("name", "=", "base")],
                ["latest_version"],
            )[0]
            .get("latest_version")
        )
        return OdooVersion(cast(str, version))

    @property
    def edition(self) -> Literal["community", "enterprise"]:
        has_enterprise_modules = bool(
            self.rpc["ir.module.module"].search_count(
                [
                    ("license", "=like", "OEEL-%"),
                    ("state", "=", "installed"),
                ]
            )
        )

        if has_enterprise_modules:
            return "enterprise"
        return "community"

    @property
    def filestore(self) -> Optional[Filestore]:
        return None

    @property
    def size(self) -> int:
        return 0

    @property
    def expiration_date(self) -> Optional[datetime]:
        date = (
            self.rpc["ir.config_parameter"]
            .search_read([("key", "=", "database.expiration_date")], ["value"])[0]
            .get("value")
        )
        return datetime.strptime(date, DATETIME_FORMAT) if isinstance(date, str) else None

    @property
    def uuid(self) -> Optional[str]:
        return cast(
            str, self.rpc["ir.config_parameter"].search_read([("key", "=", "database.uuid")], ["value"])[0].get("value")
        )

    @property
    def last_access_date(self) -> Optional[datetime]:
        date = (
            self.rpc["res.users.log"]
            .search_read([], ["create_date"], order="create_date desc", limit=1)[0]
            .get("create_date")
        )
        return datetime.strptime(date, DATETIME_FORMAT) if isinstance(date, str) else None

    @property
    def url(self) -> str:
        return self._url

    @property
    def rpc_port(self) -> int:
        return 443 if self.url.startswith("https") else 8069

    @property
    def exists(self) -> bool:
        return True

    @property
    def running(self) -> bool:
        return self.exists

    @property
    def repository(self) -> Optional[Repository]:
        return None

    @property
    def branch(self) -> Optional[Branch]:
        return None
