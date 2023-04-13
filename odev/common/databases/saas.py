"""Odoo Online (SaaS) database class."""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from odev.common import progress, string
from odev.common.connectors import GitConnector, SaasConnector
from odev.common.databases import Branch, Database, Filestore, Repository
from odev.common.errors import ConnectorError
from odev.common.mixins import SaasConnectorMixin
from odev.common.version import ODOO_VERSION_PATTERN, OdooVersion


ODOO_DOMAIN_SUFFIX = ".odoo.com"

SAAS_REPOSITORIES: List[str] = [
    "odoo-ps/psae-custom",
    "odoo-ps/psbe-custom",
    "odoo-ps/pshk-custom",
    "odoo-ps/psus-custom",
    "odoo/ps-custom",
]


class SaasDatabase(SaasConnectorMixin, Database):
    """Odoo Online (SaaS) database class."""

    connector: SaasConnector

    _url: str = None
    """The URL of the SaaS database."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    _repository: Optional[Repository] = None
    """The repository containing custom code for the database."""

    _branch: Optional[Branch] = None
    """The branch of the repository containing custom code for the database."""

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
    def repository(self) -> Optional[Repository]:
        if self._repository is None:
            self._set_repository_branch()

        return self._repository

    @repository.setter
    def repository(self, value: Repository):
        self._repository = value

    @property
    def branch(self) -> Optional[Branch]:
        if self._branch is None:
            self._set_repository_branch()

        return self._branch

    @branch.setter
    def branch(self, value: Branch):
        self._branch = value

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

    def _set_repository_branch(self):
        """Set the repository and branch of the database."""
        info = self.store.databases.get(self)

        if info is not None and info.repository is not None:
            organization, repository = info.repository.split("/", 1)
            self._repository = Repository(organization=organization, name=repository)
            self._branch = Branch(info.branch, self._repository)

    def _select_repository_branch(self):
        """Select a repository and a branch within it from the list of available
        SaaS repositories.
        """
        repositories = self.console.checkbox(
            "In what repositories could the custom code for this database be found?",
            choices=[(repository,) for repository in SAAS_REPOSITORIES],
        )

        if not repositories:
            return

        re_branch_name = re.compile(rf"{ODOO_VERSION_PATTERN}-[a-z-_]*{self.name}[a-z-_]*")
        all_branches: List[Tuple[str, str]] = []
        matching_branches: List[Tuple[str, str]] = []

        for repository in repositories:
            git = GitConnector(repository)

            with progress.spinner(f"Fetching remote branches from GitHub for SaaS repository {repository!r}"):
                git.list_remote_branches()

            all_branches.extend(
                (
                    f"{repository}@{branch.name.split('/', 1)[1]}",
                    f"{branch.name.split('/', 1)[1]} ({repository})",
                )
                for branch in git.repository.remote().refs
            )

        for branch, display in all_branches:
            if re_branch_name.match(branch.split("@", 1)[1]) is not None:
                matching_branches.append((branch, display))

        if len(matching_branches) == 1:
            selected_branch: str = matching_branches[0][0]
        else:
            if matching_branches:
                all_branches = matching_branches
                search_message: str = f"Multiple potential branches found for database {self.name!r}, select one:"
            else:
                search_message = f"No branch found for database {self.name!r}, select one manually:"

            selected_branch = self.console.fuzzy(search_message, all_branches)

        repository, selected_branch = selected_branch.split("@", 1)
        organization, repository = repository.split("/", 1)
        self.repository = Repository(organization=organization, name=repository)
        self.branch = Branch(name=selected_branch, repository=self._repository)
        self.store.databases.set(self)
