"""Odoo SH (PaaS) database class."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import (
    Any,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import ParseResult, parse_qs, urlparse

import requests
from parsel.selector import Selector
from requests import HTTPError, Response

from odev.common import progress
from odev.common.connectors import PaasConnector
from odev.common.databases import Branch, Database, Filestore, Repository
from odev.common.errors import ConnectorError
from odev.common.logging import logging
from odev.common.mixins import PaasConnectorMixin
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


ODOO_DOMAIN_SUFFIX = ".odoo.com"


@dataclass(frozen=True)
class PaasRepository(Repository):
    """Represents a repository linked to an Odoo SH project."""

    database: "PaasDatabase"
    """Current Database instance linked to the repository."""

    name: str
    """Name of the repository."""

    organization: str
    """Name of the organization owning the repository."""

    @property
    def project(self) -> "PaasProject":
        """Return the project linked to this repository."""
        return self.database.project


@dataclass(frozen=True)
class PaasProject:
    """Represents an Odoo SH project."""

    database: "PaasDatabase"
    """Current Database instance linked to the repository."""

    name: str
    """Name of the project."""

    @property
    def url(self) -> str:
        """Return the URL of the project."""
        return f"https://www.odoo.sh/project/{self.name}"

    @property
    def repository(self) -> PaasRepository:
        """Return the repository linked to this project."""
        return self.database.repository


@dataclass(frozen=True)
class PaasBranch(Branch):
    """Represents a branch on Odoo SH."""

    database: "PaasDatabase"
    """Current Database instance linked to the repository."""

    id: int
    """ID of the branch."""

    name: str
    """Name of the branch."""

    repository: Repository
    """Repository linked to this branch."""

    @property
    def project(self) -> PaasProject:
        """Return the project linked to this branch."""
        return self.database.project


@dataclass(frozen=True)
class PaasBuild:
    """Represents a build on Odoo SH."""

    database: "PaasDatabase"
    """Current Database instance linked to the repository."""

    id: int
    """ID of the build."""

    name: str
    """Name of the build."""

    url: str
    """URL of the build."""

    status: str
    """Status of the build."""

    result: str
    """Result of the build."""

    commit: "PaasBuildCommit"
    """Commit linked to this build."""

    @property
    def latest(self) -> bool:
        """Return True if this is the latest build for the current branch."""
        return self.id == self.database.last_build_id

    @property
    def project(self) -> PaasProject:
        """Return the project linked to this build."""
        return self.database.project

    @property
    def repository(self) -> PaasRepository:
        """Return the repository linked to this build."""
        return self.database.repository

    @property
    def branch(self) -> PaasBranch:
        """Return the branch linked to this build."""
        return self.database.branch


@dataclass(frozen=True)
class PaasBuildCommit:
    """Represents a commit on Odoo SH."""

    database: "PaasDatabase"
    """Current Database instance linked to the repository."""

    hash: str
    """ID of the commit."""

    message: str
    """Message of the commit."""

    author: str
    """Author of the commit."""

    date: datetime
    """Date of the commit."""

    url: str
    """URL of the commit."""

    @property
    def project(self) -> PaasProject:
        """Return the project linked to this build."""
        return self.database.project

    @property
    def repository(self) -> PaasRepository:
        """Return the repository linked to this build."""
        return self.database.repository

    @property
    def branch(self) -> PaasBranch:
        """Return the branch linked to this build."""
        return self.database.branch

    @property
    def build(self) -> PaasBuild:
        """Return the branch linked to this build."""
        return self.database.build


@dataclass(frozen=True)
class PaasBackup:
    """Represents a backup on Odoo SH."""

    database: "PaasDatabase"
    """Current Database instance linked to the backup."""

    name: str
    """Name of the backup."""

    date: datetime

    type: Literal["automatic", "manual"]
    """Type of the backup."""

    path: str
    """Path of the backup on the remote server."""

    comment: str
    """Comment of the backup."""

    @property
    def id(self) -> str:
        """Return a unique ID for the backup."""
        return f"{self.date.strftime('%Y%m%d%H%M%S')}_{self.name}_{self.type}"

    def __eq__(self, other: Any) -> bool:
        """Return True if the backup is equal to another backup."""
        if not isinstance(other, PaasBackup):
            return False

        return self.id == other.id


class PaasDatabase(PaasConnectorMixin, Database):
    """Odoo Online (SaaS) database class."""

    connector: PaasConnector

    _platform: str = "paas"
    _platform_display: str = "Odoo SH (PaaS)"

    _input_name: str = None
    """The input string as entered by the user to search for a project or a database."""

    _input_branch: Optional[str] = None
    """The input string as entered by the user to target a specific branch after project detection."""

    _name: str = None
    """The name of the database as entered by the user or parsed from the URL."""

    _url: Optional[str] = None
    """The URL of the database."""

    _token: Optional[str] = None
    """The token used to access the support backend features for this database."""

    _project: PaasProject = None
    """The project for this database."""

    _repository_info: Mapping[str, Any] = None
    """The repository information for this database, from Odoo SH."""

    _repository: PaasRepository = None
    """The repository for this database."""

    _build_info: Mapping[str, Any] = None
    """The build information for this database, from Odoo SH."""

    _build: PaasBuild = None
    """The build for this database."""

    _branch_info: Mapping[str, Any] = None
    """The branch information for this database, from Odoo SH."""

    _branch: PaasBranch = None
    """The branch for this database."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    _backups_info: Optional[List[Mapping[str, Any]]] = None
    """The backups information for this database, from the Odoo SH worker
    running the current build.
    """

    _backups: Optional[List[PaasBackup]] = None
    """The backups for this database."""

    def __init__(self, name: str, branch: Optional[str] = None):
        """Initialize the Odoo SH database and infer its name or URL."""
        super().__init__(name)
        self._input_name = name
        self._input_branch = branch
        self._set_paas_connector()

    def __enter__(self):
        self.connector = self.paas.__enter__()
        return self

    def __exit__(self, *args):
        self.paas.__exit__(*args)

    @property
    def name(self) -> str:
        """Return the name of the database."""
        return self._name

    @name.setter
    def name(self, value: str):
        """Set the name of the database."""
        if self._name == value:
            return

        self._name = value
        self._set_paas_connector()

    @property
    def url(self) -> str:
        if self._url is None:
            if re.match(rf"^{self.repository_info['project_name']}-[\w-]+-\d+$", self.name):
                self._url = f"https://{self.name}.dev{ODOO_DOMAIN_SUFFIX}"
            else:
                self._url = f"https://{self.name}{ODOO_DOMAIN_SUFFIX}"

        return self._url

    @property
    def token(self) -> str:
        """Return the token used to access the support backend features for this database."""
        if self._token is None:
            web_support = self._get_support_backend()
            parsed = urlparse(web_support.url)

            if parsed.query:
                self._token = parse_qs(parsed.query).get("token", [None])[0]

        return self._token

    @property
    def exists(self) -> bool:
        """Whether the database exists and can be reached at the current URL."""
        return self._check_url(self.url)

    @property
    def is_odoo(self) -> bool:
        return self.exists

    @property
    def version(self) -> Optional[OdooVersion]:
        version = self.build_info.get("odoo_branch")

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
                size=self.build_info.get("size_container") * 1024,
            )

        return self._filestore

    @property
    def size(self) -> int:
        return self.build_info.get("size_database") * 1024

    @property
    def expiration_date(self) -> Optional[datetime]:
        expiration_date = self.build_info.get("db_expiration_date")
        return datetime.strptime(expiration_date, "%Y-%m-%d %H:%M:%S") if expiration_date else None

    @property
    def uuid(self) -> Optional[str]:
        return None

    @property
    def last_access_date(self) -> Optional[datetime]:
        return None

    @property
    def rpc_port(self) -> Optional[int]:
        return 443

    @property
    def project(self) -> PaasProject:
        """Return the project for this database."""
        if self._project is None:
            self._project = PaasProject(database=self, name=self.repository_info["project_name"])

        return self._project

    @property
    def repository_info(self) -> Mapping[str, Any]:
        """Return the repository information for this database."""
        if self._repository_info is None:
            self._repository_info = self._guess_project()

        return self._repository_info

    @property
    def repository(self) -> PaasRepository:
        """Return the repository for this database."""
        if self._repository is None:
            organization, name = self.repository_info["full_name"].split("/")
            self._repository = PaasRepository(
                database=self,
                name=name,
                organization=organization,
            )

        return self._repository

    @property
    def build_info(self) -> Mapping[str, Any]:
        """Return the builds information for this database."""
        if self._build_info is None:
            with progress.spinner(f"Fetching build information for database {self.name!r}"):
                self._build_info = next(
                    build for build in self.paas.builds_info() if build["url"] == self.url or build["name"] == self.name
                )

        return self._build_info

    @property
    def build(self) -> PaasBuild:
        """Return the build for this database."""
        if self._build is None:
            self._build = PaasBuild(
                database=self,
                id=self.build_info["id"],
                name=self.build_info["name"],
                url=self.build_info["url"],
                status=self.build_info["status"],
                result=self.build_info["result"],
                commit=PaasBuildCommit(
                    database=self,
                    hash=self.build_info["head_commit_id"][1],
                    message=self.build_info["head_commit_msg"],
                    author=self.build_info["head_commit_author"],
                    date=datetime.strptime(self.build_info["head_commit_timestamp"], "%Y-%m-%d %H:%M:%S"),
                    url=self.build_info["head_commit_url"],
                ),
            )

        return self._build

    @property
    def branch_info(self) -> Mapping[str, Any]:
        """Return the branch information for this database."""
        if self._branch_info is None:
            branch_id, branch_name = self.build_info.get("branch_id", [0, ""])

            with progress.spinner(f"Fetching information for branch {branch_name!r}"):
                self._branch_info = next(branch for branch in self.paas.branches_info() if branch["id"] == branch_id)
        return self._branch_info

    @property
    def branch(self) -> PaasBranch:
        """Return the branch for this database."""
        if self._branch is None:
            self._branch = PaasBranch(
                database=self,
                id=self.branch_info["id"],
                name=self.branch_info["name"],
                repository=self.repository,
            )

        return self._branch

    @property
    def backups_info(self) -> List[Mapping[str, Any]]:
        """Return the backups information for this database."""
        if self._backups_info is None:
            with progress.spinner(f"Fetching backups information for database {self.name!r}"):
                self._backups_info: List[Mapping[str, Any]] = [
                    info
                    for info in self.paas.rpc(self.backups_url, params={"token": self.token})
                    if info["branch"] == self.branch.name and info["downloadable"] is True
                ]

        return self._backups_info

    @property
    def backups(self) -> List[PaasBackup]:
        """Return the backups for this database."""
        if self._backups is None:
            self._backups = [
                PaasBackup(
                    database=self,
                    name=backup["name"],
                    path=backup["path"],
                    type=backup["type"].lower(),
                    comment=backup["comment"] or "",
                    date=datetime.strptime(backup["backup_datetime_utc"], "%Y-%m-%d %H:%M:%S"),
                )
                for backup in self.backups_info
            ]

        return sorted(self._backups, key=lambda b: b.date, reverse=True)

    @property
    def commit(self) -> PaasBuildCommit:
        """Return the commit for this database."""
        return self.build.commit

    @property
    def environment(self) -> Literal["production", "staging", "development"]:
        """Return the environment of the database."""
        return self.branch_info.get("stage")

    @property
    def subscription_url(self) -> str:
        """Return the URL of the subscription."""
        if self.environment == "production":
            build = self.build_info
        else:
            build = next(build for build in self.paas.builds_info() if build["stage"] == "production")

        return build.get("enterprise_code_url")

    @property
    def monitoring_url(self) -> str:
        """Return the monitoring URL of the database."""
        return self.build_info.get("monitoring_url")

    @property
    def status_url(self) -> str:
        """Return the status URL of the database."""
        return self.build_info.get("status_url")

    @property
    def worker_url(self) -> str:
        """Return the worker URL of the database."""
        return self.build_info.get("worker_url")

    @property
    def backups_url(self) -> str:
        """Return the backups URL of the database."""
        return f"{self.worker_url}/paas/build/{str(self.build.id)}/backups/list?branch={self.branch.name}"

    @property
    def dump_path(self) -> str:
        """Return the URL path for downloading a backup of the database."""
        return f"/build/{str(self.build.id)}/dump"

    @property
    def webshell_url(self) -> str:
        """Return the webshell URL of the database."""
        return self.build_info.get("webshell_url")

    @property
    def last_build_id(self) -> int:
        """Return the ID of the last build."""
        return self.branch_info.get("last_build_id", [0, ""])[0]

    @property
    def is_last_build(self) -> bool:
        """Return whether the current build is the last build."""
        return self.build_id == self.last_build_id

    def switch_branch(self, branch: str):
        """Target the connector to another branch.
        This has the effect of changing the database name, URL and other build information.
        :param branch: The name of the branch to switch to.
        """
        if self._branch_info is not None and branch == self._branch_info["name"]:
            return

        with progress.spinner(f"Switching to branch {branch!r}"):
            branch_info = next((info for info in self.paas.branches_info() if info["name"] == branch), None)

            if branch_info is None:
                raise ConnectorError(
                    f"Branch {branch!r} not found in repository {self.repository_info['full_name']!r}",
                    self.paas,
                )

            self._name = branch_info["last_build_id"][1]
            self._url = None

    def _set_name(self, name: str):
        """Set the database name and URL from a given input."""
        parsed = self._parse_url(name)
        self._url = f"{parsed.scheme}://{parsed.netloc}"
        self._name = re.sub(rf"(\.dev)?{re.escape(ODOO_DOMAIN_SUFFIX)}$", "", parsed.netloc)

    def _set_paas_connector(self):
        """Set the PaaS connector for this database."""
        self.paas = self._paas("odev")

        if self._name is None or self._url is None:
            self._set_name(self._input_name)

        if self._input_name != self.repository_info["project_name"]:
            self._set_name(self.repository_info["project_name"])

        self.paas = self._paas(self.repository_info["full_name"])

        if self._input_branch is not None:
            self.switch_branch(self._input_branch)

        self._name = self.build.name
        self._url = self.build.url

    def _parse_url(self, url: str) -> ParseResult:
        """Parse the given URL."""
        parsed = urlparse(url, scheme="https")

        if not parsed.netloc and parsed.path:
            parsed = parsed._replace(netloc=parsed.path, path="")

        if "." not in parsed.netloc:
            parsed = parsed._replace(netloc=f"{parsed.netloc}{ODOO_DOMAIN_SUFFIX}")

        return parsed

    def _check_url(self, url: str) -> bool:
        """Check whether the given URL is a valid Odoo SH database URL."""
        parsed = self._parse_url(url)

        if not parsed.netloc.endswith(ODOO_DOMAIN_SUFFIX):
            return False

        formatted_url = f"{parsed.scheme}://{parsed.netloc}/"
        response = requests.head(formatted_url)
        location = response.headers.get("Location", "")
        return not self._parse_url(location).path.startswith("/typo")

    def _guess_project(self) -> Mapping[str, Any]:
        """Guess the name of the Odoo SH project based on the database name or URL."""
        if self.exists:
            return self._guess_project_from_url()

        return self._guess_project_from_name()

    def _guess_project_from_url(self) -> Mapping[str, Any]:
        """Guess the name of a project based on the database URL."""
        web_support = self._get_support_backend()
        selector = Selector(text=web_support.text)

        database_name = selector.xpath("//div[@id='support-welcome']/h2/a/text()").get()

        if database_name is not None and database_name != self.name:
            self._name = database_name

        selection_url = selector.xpath(
            "//div[@id='odoo-sh-database']//a[contains(@href, '/support/selection?technical_name')]"
        ).attrib.get("href")

        if selection_url is None:
            raise ConnectorError(f"Cannot guess the project name for database {self.name!r}", self.paas)

        parsed = urlparse(selection_url)

        with self.paas.with_url(f"{parsed.scheme}://{parsed.netloc}"):
            web_selection = self.paas.get(
                parsed.path,
                params={key: value[0] for key, value in parse_qs(parsed.query).items()},
            )

        repository_id = (
            Selector(text=web_selection.text).xpath("//form//input[@name='repository_id']").attrib.get("value")
        )

        if repository_id is None or not repository_id.isdigit():
            raise ConnectorError(f"Cannot find repository ID for database {self.name!r}", self.paas)

        return next(
            repository for repository in self.paas.list_repositories() if repository["id"] == int(repository_id)
        )

    def _guess_project_from_name(self) -> Mapping[str, Any]:
        """Guess the name of the Odoo SH project based on the database name."""
        split = self.name.split("-")
        repositories: List[Mapping[str, Any]] = []

        while split and not repositories:
            filtered_repositories = self.paas._filter_repositories("-".join(split))

            if filtered_repositories:
                repositories = filtered_repositories

            split.pop()

        if not repositories:
            raise ConnectorError(f"Cannot guess the project name for database {self.name!r}", self.paas)

        if len(repositories) > 1:
            selected = self.console.select(
                f"Multiple projects found for database {self.name!r}:",
                choices=[
                    (repo["project_name"], f"{repo['project_name']} ({repo['full_name']})") for repo in repositories
                ],
            )

            return next(repo for repo in repositories if repo["project_name"] == selected)

        return repositories[0]

    def _get_support_backend(self) -> Response:
        """Return the support page of the database."""
        cached = self.paas.cache(f"GET:{self.url + self.paas.support_path}:{{}}")

        if cached is not None:
            return cached

        with self.paas.nocache():
            with self.paas.with_url(self.url):
                web_login = self.paas.get(self.paas.support_path, authenticate=False)

            if self._parse_url(web_login.url).path == self.paas.support_path:
                return web_login

            fields = self.paas.extract_form_inputs(web_login)
            fields.update({"login": self.paas.login, "password": self.paas.password})

            web_login = self.paas.post(self.paas.login_path, authenticate=False, data=fields)
            web_login_path: str = urlparse(web_login.url).path

            if web_login.status_code != 200 or web_login_path == self.paas.login_path:
                logger.warning("Failed to log in to Odoo SH, please check your credentials")
                self.store.secrets.get("odoo.com:pass", prompt_format="Odoo account {field}:", force_ask=True)
                return self._get_support_page()
            elif web_login_path != self.paas.support_path:
                # Obfuscate the password before raising because locals are
                # displayed in tracebacks
                fields.update({"password": "*****"})
                raise ConnectorError("Unexpected redirect after logging in to Odoo SH")

        with self.paas.with_url(self.url):
            return self.paas.get(self.paas.support_path)

    def dump(self, filestore: bool = False, test: bool = True, path: Path = None) -> Optional[Path]:
        """Download a backup of the database.
        :param filestore: Whether to include the filestore in the backup.
        :param test: Whether to download a testing or an exact dump.
        :param path: The path where to store the backup.
        :return: The path to the downloaded backup.
        :rtype: Path
        """
        if path is None:
            path = self.odev.dumps_path

        path.mkdir(parents=True, exist_ok=True)
        filename = self._get_dump_filename(
            filestore=filestore,
            test=test,
            suffix=self.platform.name,
        )
        file = path / filename

        if file.exists() and not self.console.confirm(f"File {file} already exists. Overwrite it?"):
            return None

        file.unlink(missing_ok=True)
        self._download_backup(file, filestore=filestore, test=test)
        return file

    def _get_dump_filename(
        self,
        filestore: bool = False,
        test: bool = True,
        suffix: str = None,
        extension: str = "zip",
    ) -> str:
        """Return the filename of the dump file.
        :param filestore: Whether to include the filestore in the dump.
        :param test: Whether to download a testing or an exact dump.
        :param suffix: An optional suffix to add to the filename.
        :param extension: The extension of the dump file.
        :return: The filename of the dump file.
        :rtype: str
        """
        prefix = datetime.now().strftime("%Y%m%d")
        suffix = f".{suffix}" if suffix else ""
        suffix += f".{'' if filestore else 'no'}fs.{'neutralized' if test else 'exact'}"
        return f"{prefix}-{self.name}.dump{suffix}.{extension}"

    def _select_backup(self, filestore: bool = False, test: bool = True) -> PaasBackup:
        """Select a backup to download amongst those already available on the worker,
        or create a new backup to download.
        :param filestore: Whether to include the filestore in the backup.
        :param test: Whether to download a testing or an exact dump.
        """
        choices: List[Tuple[Union[PaasBackup, None], str]] = [(None, "Create a new manual backup")]
        choices += [
            (
                b,
                f"[{b.date.strftime('%Y-%m-%d %X UTC')}] "
                f"{b.name + (f': {b.comment}' if b.comment else '')} "
                f"({b.type})",
            )
            for b in self.backups
        ]

        if self.backups:
            selected: Optional[PaasBackup] = self.console.select(
                f"Existing backup(s) found for database {self.name!r}:",
                choices=choices,
            )

            if selected is not None:
                return PaasBackup(**selected) if isinstance(selected, dict) else selected

        self._create_backup(filestore, test)
        return self.backups[0]

    def _refresh_backups(self) -> List[PaasBackup]:
        """Refresh the list of backups available on the remote worker."""
        logger.debug(f"Refreshing backups list for database {self.name!r}")
        self._backups_info = None
        self._backups = None

        with self.paas.nocache():
            return self.backups

    def _count_backup_notifications(self) -> int:
        """Return the number of dump ready notifications in the notifications list."""
        with self.paas.nocache():
            return self.paas.count_backup_notifications()

    def _create_backup(self, filestore: bool = False, test: bool = True, date: datetime = None):
        """Create a new backup for the database on the remote worker
        and wait for the dump to be ready.
        :param filestore: Whether to include the filestore in the backup.
        :param test: Whether to create a testing or an exact dump.
        """
        action = "Creating new manual backup" if date is None else "Preparing backup download"

        with progress.spinner(f"{action} for database {self.name!r}"):
            notifications_count: int = self._count_backup_notifications()
            params: MutableMapping[str, str] = {
                "backup_only": "0",
                "filestore": str(int(filestore)),
                "test_dump": str(int(test)),
            }

            if date is not None:
                params["backup_datetime_utc"] = date.strftime("%Y-%m-%d %H:%M:%S")

            self.paas.rpc(self.dump_path, params=params)

            while self._count_backup_notifications() <= notifications_count:
                sleep(5)

            self._refresh_backups()

    def _download_backup(
        self,
        path: Path,
        filestore: bool = False,
        test: bool = True,
        backup: Optional[PaasBackup] = None,
    ) -> Path:
        """Download the backup from the remote worker.
        :param filestore: Whether to include the filestore in the backup.
        :param test: Whether to download a testing or an exact dump.
        """
        backup = backup or self._select_backup(filestore, test)
        dump_url = f"{self.worker_url}/paas/build/{self.build.id}/download/dump"
        dump_params = {
            "backup_datetime_utc": backup.date.strftime("%Y-%m-%d %H:%M:%S"),
            "test_dump": int(test),
            "filestore": int(filestore),
            "token": self.token,
        }

        progress_message = (
            f"Dumping database [repr.url]{self.url}[/repr.url] {'with' if filestore else 'without'} filestore"
        )

        try:
            return self.paas.download(
                dump_url,
                path,
                progress_message=progress_message,
                params=dump_params,
                retry=False,
            )
        except HTTPError:
            self._create_backup(filestore, test, date=backup.date)
            return self._download_backup(path, filestore, test, backup)
