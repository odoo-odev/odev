"""Module to manage Odoo processes."""

import re
import shlex
from ast import literal_eval
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import TYPE_CHECKING, Literal, cast

from packaging.version import Version

from odev.common import bash, string
from odev.common.connectors import GitConnector, GitWorktree
from odev.common.databases import Branch, Repository
from odev.common.databases.remote import RemoteDatabase
from odev.common.debug import find_debuggers
from odev.common.errors import OdevError
from odev.common.logging import LOG_LEVEL, logging, silence_loggers
from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.progress import spinner
from odev.common.python import PythonEnv
from odev.common.signal_handling import capture_signals
from odev.common.version import OdooVersion


if TYPE_CHECKING:
    from odev.common.databases import LocalDatabase


__all__ = ["ODOO_PYTHON_VERSIONS", "OdoobinProcess"]


logger = logging.getLogger(__name__)


ODOO_COMMUNITY_REPOSITORIES: list[str] = [
    "odoo/odoo",
    "odoo/design-themes",
]

ODOO_ENTERPRISE_REPOSITORIES: list[str] = ["odoo/enterprise"]

ODOO_PYTHON_VERSIONS: Mapping[int, str] = {
    19: "3.12",
    16: "3.10",
    14: "3.8",
    11: "3.7",
    0: "2.7",
}


def odoo_repositories(enterprise: bool = True) -> Generator[GitConnector, None, None]:
    """List of Odoo repositories depending on the edition passed."""
    repo_names: list[str] = [*ODOO_COMMUNITY_REPOSITORIES]

    if enterprise:
        for repo_name in ODOO_ENTERPRISE_REPOSITORIES:
            repo_names.insert(1, repo_name)

    for repo_name in repo_names:
        yield GitConnector(repo_name)


class OdoobinProcess(OdevFrameworkMixin):
    """Class to manage an odoo-bin process."""

    _processes_cache: dict[str, str] = {}
    _processes_cache_timestamp: datetime = datetime.min

    def __init__(
        self,
        database: "LocalDatabase",
        venv: str | None = None,
        worktree: str | None = None,
        version: OdooVersion | None = None,
    ):
        """Initialize the OdoobinProcess object."""
        super().__init__()

        self.database: LocalDatabase = database
        """Database this process is for."""

        self._version: OdooVersion | None = version or self.database.version or OdooVersion("master")
        """Force the version of Odoo when running the process."""

        odoo_branch = self._get_version()

        self._forced_venv_name: str | None = venv
        """Forced name of the virtual environment to use."""

        self._venv_name: str = odoo_branch
        """Name of the virtual environment to use."""

        self._forced_worktree_name: str | None = worktree
        """Forced name of the worktree to use."""

        self._worktree_name: str = odoo_branch
        """Name of the worktree to use."""

        self.repository: GitConnector = GitConnector("odoo/odoo")
        """Github repository of Odoo."""

        self._additional_addons_paths: list[Path] = []
        """List of additional addons paths to use when starting the Odoo process."""

        self._venv: PythonEnv | None = None
        """Cached python virtual environment used by the Odoo installation."""

        self._force_enterprise: bool = False
        """Force using the enterprise version of Odoo."""

    def __repr__(self) -> str:
        return (
            "OdoobinProcess("
            f"database={self.database.name!r}, "
            f"version={self.version!r}, "
            f"venv={self.venv!r}, "
            f"worktree={self.worktree!r}, "
            f"pid={self.pid!r}"
            ")"
        )

    @classmethod
    def get_psql_version(cls) -> Version | None:
        """Return the version of psql installed on the system."""
        process = bash.execute("psql --version")

        if process is not None and process.returncode == 0:
            match = re.search(r"(\d+\.\d+)", process.stdout.decode())

            if match is not None:
                return Version(match.group(1))

        return None

    @property
    def venv(self) -> PythonEnv:
        """Python virtual environment used by the Odoo installation."""
        if self._venv is None:
            self._venv = PythonEnv(self.venv_path, self._get_python_version())

        return self._venv

    @property
    def version(self) -> OdooVersion | None:
        """Version of Odoo running in this process."""
        if self._version is not None:
            return self._version

        if not self.database.exists:
            return None

        with self.database:
            return self.database.version

    @property
    def worktree(self) -> str:
        """Name of the worktree used to run the Odoo database."""
        return self._forced_worktree_name or self._worktree_name

    @property
    def odoo_path(self) -> Path:
        """Path to the Odoo installation."""
        for worktree in self.odoo_worktrees:
            if worktree.name == self.worktree and worktree.connector.name == ODOO_COMMUNITY_REPOSITORIES[0]:
                return worktree.path

        self.update_worktrees()
        return self.odoo_path

    @property
    def odoobin_path(self) -> Path:
        """Path to the odoo-bin executable."""
        odoo_bin = self.odoo_path / "odoo-bin"

        if not odoo_bin.exists():
            return self.odoo_path / "odoo.py"

        return odoo_bin

    @property
    def venv_path(self):
        """Path to the virtual environment of the Odoo installation."""
        return self.odev.home_path / "virtualenvs" / str(self._forced_venv_name or self._venv_name)

    @property
    def pid(self) -> int | None:
        """Return the process id of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        pid = re.split(r"\s+", process)[1]

        if not pid or not pid.isdigit():
            return None

        return int(pid)

    @property
    def command(self) -> str | None:
        """Return the command of the process of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return " ".join(re.split(r"\s+", process)[10:])

    @property
    def rpc_port(self) -> int | None:
        """Return the RPC port of the process of the current database if it is running."""
        if not self.command:
            return None

        match = re.search(r"(?:-p|--http-port)(?:\s+|=)([0-9]{1,5})", self.command)
        return int(match.group(1)) if match is not None else 8069

    @property
    def is_running(self) -> bool:
        """Return whether Odoo is currently running on the database."""
        return self.pid is not None

    @property
    def odoo_repositories(self) -> Generator[GitConnector, None, None]:
        """Return the list of Odoo repositories the current version."""
        return odoo_repositories(self.database.edition == "enterprise" or self._force_enterprise)

    @property
    def odoo_support_repository(self) -> GitConnector:
        """Return a connector to the odoo/support-tools repository."""
        return GitConnector("odoo/support-tools")

    @property
    def additional_addons_paths(self) -> list[Path]:
        """Return the list of additional addons paths."""
        if not self._additional_addons_paths and self.database.repository:
            repository = GitConnector(self.database.repository.full_name)

            if repository.path not in self._additional_addons_paths:
                self._additional_addons_paths.append(repository.path)

        return self._additional_addons_paths

    @additional_addons_paths.setter
    def additional_addons_paths(self, value: list[Path]):
        """Set the list of additional addons paths."""
        self._additional_addons_paths = value

    @property
    def additional_repositories(self) -> Generator[GitConnector, None, None]:
        """Return the list of additional repositories linked to this database."""
        for path in self.additional_addons_paths:
            if (path / ".git").exists() and self.check_addons_path(path):
                yield GitConnector(f"{path.parent.name}/{path.name}")

    @property
    def odoo_worktrees(self) -> Generator[GitWorktree, None, None]:
        """Return the list of Odoo worktrees for the current version."""
        for repository in self.odoo_repositories:
            for worktree in repository.worktrees():
                if worktree.name == self.worktree:
                    yield worktree

    @property
    def odoo_addons_paths(self) -> list[Path]:
        """Return the list of Odoo addons paths."""
        return [
            worktree.path / addon
            for addon in ["", "addons", "odoo/addons", "openerp/addons"]
            for worktree in self.odoo_worktrees
            if OdoobinProcess.check_addons_path(worktree.path / addon)
        ]

    @property
    def addons_paths(self) -> list[Path]:
        """Return the list of addons paths."""
        return [
            path.expanduser()
            for path in self.odoo_addons_paths + self.additional_addons_paths
            if OdoobinProcess.check_addons_path(path)
        ]

    @property
    def addons_requirements(self) -> Generator[Path, None, None]:
        """Return the list of addons requirements files."""
        globs = (
            path.glob("**/requirements.txt")
            for path in (
                self.addons_paths
                + [Path(__file__).parents[1] / "static"]
                + [worktree.path for worktree in self.odoo_worktrees]
            )
        )
        return (path for glob in globs for path in glob if not re.search(r"/iot.*/requirements.txt$", str(path)))

    def with_edition(self, edition: Literal["community", "enterprise"] | None = None) -> "OdoobinProcess":
        """Return the OdoobinProcess instance with the given edition forced."""
        if edition is None:
            edition = "enterprise"

        self._force_enterprise = edition == "enterprise"
        return self

    def with_venv(self, venv: PythonEnv | str) -> "OdoobinProcess":
        """Return the OdoobinProcess instance with the given virtual environment forced."""
        self._forced_venv_name = venv.name if isinstance(venv, PythonEnv) else venv
        self._venv = None
        return self

    def with_version(self, version: OdooVersion | None = None) -> "OdoobinProcess":
        """Return the OdoobinProcess instance with the given version forced."""
        if version is None:
            version = OdooVersion("master")

        self._version = version
        self._venv_name = self._worktree_name = str(version)
        self._venv = None
        return self

    def with_worktree(self, worktree: str) -> "OdoobinProcess":
        """Return the OdoobinProcess instance with the given worktree forced."""
        self._forced_worktree_name = worktree
        return self

    def _get_ps_process(self) -> str | None:
        """Return the process currently running odoo, if any.
        Grep-ed `ps aux` output.
        """
        if datetime.now() - OdoobinProcess._processes_cache_timestamp < timedelta(seconds=5):
            return OdoobinProcess._processes_cache.get(self.database.name)

        process = bash.execute("ps aux | grep odoo-bin || echo -n ''")
        OdoobinProcess._processes_cache = {}
        OdoobinProcess._processes_cache_timestamp = datetime.now()

        if process is not None:
            for line in process.stdout.decode().splitlines():
                match = re.search(r"odoo-bin\s+.*(?:-d|--database)(?:\s+|=)(?P<db>[^\s]+)", line)
                if match:
                    OdoobinProcess._processes_cache[match.group("db")] = line

        return OdoobinProcess._processes_cache.get(self.database.name)

    def _get_python_version(self) -> str | None:
        """Return the Python version used by the current Odoo installation."""
        if self.version is None:
            return None

        if self.version == OdooVersion("master"):
            return ODOO_PYTHON_VERSIONS.get(max(ODOO_PYTHON_VERSIONS.keys()), None)

        return ODOO_PYTHON_VERSIONS.get(
            min(ODOO_PYTHON_VERSIONS, key=lambda v: abs(v - cast(OdooVersion, self.version).major)), None
        )

    def _get_version(self) -> str:
        """Return the branch of the current Odoo installation."""
        if self.version is None:
            return "master"

        return str(self.version)

    def kill(self, hard: bool = False):
        """Kill the process of the current database.

        :param hard: Send a SIGKILL instead of a SIGTERM to the running process.
        """
        if self.pid is not None:
            bash.execute(f"kill -{9 if hard else 2} {self.pid}")

    def supports_subcommand(self, subcommand: str) -> bool:
        """Return whether the given subcommand is supported by the current version of Odoo.

        :param subcommand: Subcommand to check.
        :return: True if the subcommand is supported, False otherwise.
        :rtype: bool
        """
        if not self.venv.exists:
            self.prepare_venv()

        with self.console.capture() as output:
            process = self.run(["-h"], subcommand=subcommand, stream=False, prepare=False)

        return process is not None and "Unknown command" not in output.get()

    def prepare_odoobin_args(self, args: list[str] | None = None, subcommand: str | None = None) -> list[str]:
        """Prepare the arguments to pass to odoo-bin.

        :param args: Additional arguments to pass to odoo-bin.
        :param subcommand: Subcommand to pass to odoo-bin.
        :return: List of arguments to pass to odoo-bin.
        :rtype: List[str]
        """
        home_path = Path("~").expanduser().as_posix()
        addons_paths = ",".join(re.sub(rf"^{home_path}", "~", path.as_posix()) for path in self.addons_paths)

        odoo_bin_args: list[str] = []
        odoo_bin_args.extend(["--database", self.database.name])
        odoo_bin_args.extend(["--addons-path", addons_paths])
        odoo_bin_args.extend(["--log-level", LOG_LEVEL.lower()])
        odoo_bin_args.extend(args or [])

        if subcommand is not None:
            odoo_bin_args.insert(0, subcommand)

        return odoo_bin_args

    def prepare_odoobin(self):
        """Prepare the odoo-bin executable and ensure all dependencies are installed."""
        if self.version is None:
            logger.warning("No version specified, skipping environment setup")
            return

        with spinner(f"Preparing worktree {self.worktree!r}"):
            self.update_worktrees()

        with spinner(f"Preparing virtual environment {self.venv.name!r}"):
            self.prepare_venv()
            self.prepare_npm()
            self.prepare_psql()

    def format_command(
        self,
        args: list[str] | None = None,
        subcommand: str | None = None,
        subcommand_input: str | None = None,
    ) -> str:
        """Format the command to run the Odoo process.
        :param args: Additional arguments to pass to odoo-bin
        :param subcommand: Subcommand to pass to odoo-bin.
        :param subcommand_input: Input to pipe to the subcommand.
        """
        line_separator = string.stylize("\\\n", "color.black")
        odoobin_args = self.prepare_odoobin_args(args, subcommand)
        formatted_args = "".join(
            [
                re.sub(r"(-+[\w-]+)(?:\s+|=)?(.*)", r"[color.black]\1[/color.black] \2", arg).strip()
                + " "
                + line_separator
                for arg in re.split(r"\s(?=-{1,2}[^\d])", " ".join(odoobin_args[int(bool(subcommand)) :]))
            ]
        ).removesuffix(line_separator)

        formatted_command = f"{self.venv.python} {self.odoobin_path}"

        if subcommand:
            formatted_command += f" {subcommand}"

        formatted_command += f" {line_separator}{string.indent(formatted_args, 4)}"

        if subcommand_input:
            pipe = string.stylize("|", "color.black")
            formatted_command = f"{subcommand_input} {pipe}{line_separator}{formatted_command}"

        return formatted_command + "\n"

    def deploy(
        self,
        module: Path,
        args: list[str] | None = None,
        url: str | None = None,
    ) -> CompletedProcess | None:
        """Run odoo-bin deploy to import a module on the database at the given URL.
        :param args: Additional arguments to pass to odoo-bin.
        :param url: URL of the database to which import the module.
        """
        if args is None:
            args = []

        database: LocalDatabase | RemoteDatabase

        if url is None:
            database = self.database
        else:
            database = RemoteDatabase(url)

            if "--db" not in args:
                args.extend(["--db", database.name])

            secret = self.odev.store.secrets.get(database.url, scope="user", platform="remote")

            if "--login" not in args:
                args.extend(["--login", shlex.quote(secret.login)])

            if "--password" not in args:
                args.extend(["--password", shlex.quote(secret.password)])

        if not database.is_odoo:
            raise OdevError("Cannot deploy onto a non-odoo database")

        odoo_subcommand: str = "deploy"
        odoo_command: str = f"odoo-bin {odoo_subcommand}"
        odoo_args: list[str] = [
            odoo_subcommand,
            *args,
            module.as_posix(),
            cast(str, database.url),
        ]

        info_message: str = (
            f"Running {odoo_command!r} in version {database.version!s} "
            f"on {database.platform.display} database {database.name!r}"
        )

        logger.info(f"{info_message} using command:")
        sanitized_args = re.sub(r"--password\s[^\s]+", "--password *****", " ".join(odoo_args))
        formatted_command = f"{self.venv.python} {self.odoobin_path} {sanitized_args}"
        self.console.print(f"\n{string.stylize(formatted_command, 'color.cyan')}\n", soft_wrap=True)

        with capture_signals():
            try:
                with spinner(info_message):
                    process = self.venv.run_script(self.odoobin_path, odoo_args, stream=False)
            except CalledProcessError as error:
                error_message: str = error.stderr.strip().decode().rstrip(".").replace("ERROR: ", "")
                logger.error(f"Odoo exited with an error: {error_message}")
                return None
            else:
                return process

    def run(  # noqa: PLR0913
        self,
        args: list[str] | None = None,
        subcommand: str | None = None,
        subcommand_input: str | None = None,
        stream: bool = True,
        progress: Callable[[str], None] | None = None,
        prepare: bool = True,
    ) -> CompletedProcess | None:
        """Run Odoo on the current database.

        :param args: Additional arguments to pass to odoo-bin.
        :param subcommand: Subcommand to pass to odoo-bin.
        :param subcommand_input: Input to pipe to the subcommand.
        :param stream: Whether to stream the output of the process.
        :param progress: Callback to call on each line outputted by the process. Ignored if `stream` is False.
        :param prepare: Whether to prepare the environment before running the process.
        :return: The return result of the process after completion.
        :rtype: subprocess.CompletedProcess
        """
        if self.is_running and subcommand is None:
            raise OdevError("Odoo is already running on this database")

        if prepare:
            with spinner(f"Preparing odoo-bin version {str(self.version)!r} for database {self.database.name!r}"):
                self.prepare_odoobin()

        if stream and progress is not None:
            with spinner("Looking for calls to interactive debuggers"):
                debuggers = [f"{file.as_posix()}:{line}" for file, line in self.addons_debuggers()]

            if debuggers:
                logger.warning(f"Interactive debuggers detected in addons:\n{string.join_bullet(debuggers)}")
                logger.warning("Disabling logs prettifying to avoid interfering with the debugger")
                progress = None

        with capture_signals():
            odoo_command = f"odoo-bin {subcommand}" if subcommand is not None else "odoo-bin"
            odoobin_args = self.prepare_odoobin_args(args, subcommand)
            formatted_command = self.format_command(args, subcommand, subcommand_input)
            info_message = f"Running {odoo_command!r} in version '{self.version!s}' on database {self.database.name!r}"
            logger.info(f"{info_message} using command:")
            self.console.print()
            self.console.print(formatted_command, soft_wrap=True, highlight=False)

            try:
                with spinner(info_message) if not stream else nullcontext():  # type: ignore[attr-defined]
                    self.database.venv = self.venv
                    self.database.worktree = self.worktree
                    process = self.venv.run_script(
                        self.odoobin_path,
                        odoobin_args,
                        stream=stream,
                        progress=progress,
                        script_input=subcommand_input,
                    )
            except CalledProcessError as error:
                if not stream:
                    self.console.print(error.stderr.decode())

                if self.odev.in_test_mode:
                    logger.debug(f"STDOUT: {error.stdout.decode()}")
                    logger.error(f"STDERR: {error.stderr.decode()}")

                logger.error("Odoo exited with an error, check the output above for more information")
                return None
            else:
                return process

    def prepare_psql(self):
        """Prepare the PostgreSQL for the Odoo installation.
        Mainly, check that the installed version is supported.
        """
        logger.debug("Verifying PostgreSQL installation")

        with silence_loggers("odev.common.bash"):
            psql_version = self.get_psql_version()

        if psql_version is None:
            raise OdevError("PostgreSQL is not installed, please install it first")

        if self.version is None:
            logger.warning("No version specified, skipping PostgreSQL version check")
            return

        if self.version >= OdooVersion("19.0") and psql_version < Version("16.0"):
            raise OdevError(f"Odoo {self.version} requires PostgreSQL 16 or higher, current version is {psql_version}")

    def prepare_npm(self):
        """Prepare the packages of the Odoo installation."""
        logger.debug("Verifying NPM installation")

        with silence_loggers("odev.common.bash"):
            npm_process = bash.execute("which npm", raise_on_error=False)

        if npm_process is None or npm_process.returncode:
            raise OdevError("NPM is not installed, please install it first")

        packages = ["rtlcss"]

        if cast(OdooVersion, self.version).major <= 10:  # noqa: PLR2004
            packages.extend(["less", "less-plugin-clean-css"])

        missing = list(self.missing_npm_packages(packages))

        if any(missing):
            bash.execute(f"cd {self.odoo_path} && npm install {' '.join(missing)}")

    def missing_npm_packages(self, packages: Sequence[str]) -> Generator[str, None, None]:
        """Check whether the given NPM packages are installed in the version folder of Odoo."""
        installed_packages_process = bash.execute(f"cd {self.odoo_path} && npm list")

        if installed_packages_process is None:
            raise OdevError("Failed to check installed NPM packages")

        installed_packages = installed_packages_process.stdout.decode()

        for package in packages:
            if f" {package}" not in installed_packages:
                yield package

    def prepare_venv(self):
        """Prepare the virtual environment of the Odoo installation."""
        if not self.database.exists:
            raise OdevError("Database does not exist")

        if not self.venv.exists:
            self.venv.create()
            self.venv.install_packages(["wheel", "setuptools", "pip", "cython<3.0.0"])
            self.venv.install_packages(["pyyaml==5.4.1"], ["--no-build-isolation"])

        for path in self.addons_requirements:
            missing_gevent = next(
                (line for line in self.venv.missing_requirements(path) if line.startswith("gevent")),
                None,
            )

            if missing_gevent:
                self.venv.install_packages([missing_gevent.split(" ;")[0]], ["--no-build-isolation"])

            if any(self.venv.missing_requirements(path)):
                self.venv.install_requirements(path)

        if not isinstance(self.version, OdooVersion):
            raise TypeError("Cannot prepare the virtual environment for an unknown version of Odoo")

        if self.version.major < 10 and not self.version.master:  # noqa: PLR2004
            self.venv.install_packages(["psycopg2==2.7.3.1"])

    def outdated_odoo_worktrees(self) -> Generator[GitWorktree, None, None]:
        """Return the Odoo repositories with pending changes."""
        for worktree in self.odoo_worktrees:
            if worktree.detached or worktree.branch not in worktree.repository.remotes[0].refs:
                continue

            commits_behind, _ = worktree.pending_changes()

            if commits_behind:
                yield worktree

    def update_worktrees(self):
        """Update the worktrees of the Odoo repositories."""
        self.clone_repositories()

        for repository in self.odoo_repositories:
            repository.prune_worktrees()

            if len(list(self.odoo_repositories)) != len(list(self.odoo_worktrees)):
                repository.create_worktree(f"{self.worktree}/{repository.path.name}", str(self.version or "master"))

        # Pull changes once per week, on Monday (or a later day if odev was not run)
        pull_date = self.odev.config.repositories.date
        next_monday = pull_date + timedelta(days=(7 - pull_date.weekday()))
        next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        today = datetime.today()

        if next_monday > today:
            return logger.debug(
                f"Skipping worktree update, next pull scheduled in {(next_monday - today).days + 1} days"
            )

        outdated_worktrees = list(self.outdated_odoo_worktrees())

        if len(outdated_worktrees) == 1:
            worktree = outdated_worktrees[0]
            commits_behind, _ = worktree.pending_changes()
            remote_name = f"{worktree.repository.remote().name}/{worktree.branch}"

            logger.info(
                f"Repository {worktree.connector.name!r} in worktree {worktree.name!r} "
                f"is {commits_behind} commits behind {remote_name!r}"
            )

            if self.console.confirm("Pull changes now?", default=True):
                worktree.connector.pull_worktrees([worktree], force=True)

        elif outdated_worktrees:
            logger.info(f"Multiple repositories have pending changes in worktree {outdated_worktrees[0].name!r}")
            worktrees_to_pull: list[GitWorktree] = self.console.checkbox(
                "Select the repositories to update:",
                choices=[
                    (worktree, f"{worktree.connector.name} ({worktree.pending_changes()[0]} commits)")
                    for worktree in outdated_worktrees
                ],
                defaults=outdated_worktrees,
            )

            for worktree in worktrees_to_pull:
                worktree.connector.pull_worktrees(worktrees_to_pull, force=True)

        self.odev.config.repositories.date = today
        return None

    def clone_repositories(self):
        """Clone the missing Odoo repositories."""
        for repo in self.odoo_repositories:
            repo.clone()
            repo.checkout(revision="master", quiet=True)

    @classmethod
    def check_addons_path(cls, path: Path) -> bool:
        """Return whether the given path is a valid Odoo addons path.

        :param path: Path to check.
        :return: True if the path is a valid Odoo addons path, False otherwise.
        :rtype: bool
        """
        if not path.is_dir():
            return False

        globs = (path.glob(f"*/__{manifest}__.py") for manifest in ["manifest", "openerp"])
        return path.is_dir() and any(
            manifest.is_file() and (manifest.parent / "__init__.py").is_file() for glob in globs for manifest in glob
        )

    @classmethod
    def check_addon_path(cls, path: Path) -> bool:
        """Return whether the given path is a valid Odoo addon.

        :param path: Path to check.
        :return: True if the path is a valid Odoo addon path, False otherwise.
        :rtype: bool
        """
        return (path.is_dir() and (path / "__manifest__.py").exists()) or (path / "__openerp__.py").exists()

    @classmethod
    def version_from_addons(cls, path: Path) -> OdooVersion | None:
        """Find the highest Odoo version of the addons in a directory, if this is an addons directory.

        :param path: Path to the addons directory.
        """
        if not cls.check_addons_path(path):
            return None

        versions = cast(set[OdooVersion], {cls.version_from_manifest(addon) for addon in path.iterdir()} - {None})

        if not versions:
            return None

        return max(versions)

    @classmethod
    def version_from_manifest(cls, addon: Path) -> OdooVersion | None:
        """Find the Odoo version of an addon from its manifest file.

        :param addon: Path to the addon directory.
        """
        for manifest_name in ["__manifest__.py", "__openerp__.py"]:
            manifest_path = addon / manifest_name

            if not manifest_path.exists():
                continue

            manifest = cls.read_manifest(manifest_path)

            if not manifest:
                continue

            version = manifest.get("version", None)

            if isinstance(version, str):
                return OdooVersion(version)

        return None

    @classmethod
    def read_manifest(cls, path: Path) -> Mapping[str, str | list[str | int | bool]] | None:
        """Read the manifest file of an Odoo module.

        :param path: Path to the manifest file.
        """
        with path.open("r") as manifest:
            content = manifest.read()

        try:
            value = literal_eval(content)
            return value if isinstance(value, dict) else None
        except SyntaxError:
            return None

    def addons_debuggers(self) -> Generator[tuple[Path, int], None, None]:
        """Find all calls to interactive debuggers in the addons paths for the current Odoo version.
        :return: The path to the file and line where the debugger is called, if any.
        """
        odoo_base_path: Path = self.odoo_path / "odoo"
        addons_paths = {(odoo_base_path if odoo_base_path in path.parents else path) for path in self.addons_paths}

        for addon in addons_paths:
            yield from find_debuggers(addon)

    def save_database_repository(self):
        """Link the database to the first repository in additional addons-paths, allowing for reusing it in subsequent
        runs of an odoo-bin process using this database.
        """
        repository = next(self.additional_repositories, None)

        if repository is None:
            return

        info = self.database.store.databases.get(self.database)

        if info is not None and info.repository is not None:
            if info.repository == repository.name:
                return

            logger.warning(
                f"""Your are running the database {self.database.name!r} with the repository {repository.name!r}
                but it is already linked to another repository {info.repository!r}
                """
            )

            choice = self.console.select(
                "What do you want to do?",
                [
                    (
                        "keep_and_use_old",
                        f"Keep the existing repository linked and use it (run with {info.repository!r})",
                    ),
                    (
                        "keep_and_use_new",
                        f"Keep the existing repository linked but use the new one temporarily "
                        f"(run with {repository.name!r})",
                    ),
                    (
                        "replace",
                        f"Replace the existing repository with the new one and use it (run with {repository.name!r})",
                    ),
                ],
                default="keep_and_use_old",
            )

            if choice == "keep_and_use_old":
                self.additional_addons_paths = [
                    path for path in self.additional_addons_paths if path != repository.path
                ]

            elif choice == "keep_and_use_new":
                self.additional_addons_paths = [
                    path for path in self.additional_addons_paths if path != GitConnector(info.repository).path
                ]

            if choice != "replace":
                return

        self.database.repository = Repository(repository._repository, repository._organization)

        if repository.branch is not None:
            self.database.branch = Branch(repository.branch, cast(Repository, self.database.repository))

    def standardize(self, remove_studio: bool = False, dry: bool = False) -> CompletedProcess | None:
        """Remove customizations from a database using the `clean_database.py` script
        from the `odoo/support-tools` repository.
        :param remove_studio: Whether to remove Studio customizations.
        :param dry: Whether to only print the command that would be executed without running it.
        """
        if self.is_running:
            raise OdevError("Odoo is already running on this database")

        with spinner(f"Preparing Odoo {str(self.version)!r} for database {self.database.name!r}"):
            self.prepare_odoobin()
            self.odoo_support_repository.clone(revision="master")

            if any(self.venv.missing_requirements(self.odoo_support_repository.path)):
                self.venv.install_requirements(self.odoo_support_repository.path)

        with capture_signals():
            command_args: list[str] = []
            command_args.append(self.database.name)
            command_args.extend(["--addons-path-list", ",".join(path.as_posix() for path in self.addons_paths)])

            if remove_studio:
                command_args.append("--remove-studio")

            if dry:
                command_args.extend(["--dry-run", "--verbose"])

            try:
                process = self.venv.run_script(
                    self.odoo_support_repository.path / "clean_database.py",
                    command_args,
                )
            except CalledProcessError as error:
                self.console.print(error.stderr.decode())
                logger.error("Odoo exited with an error, check the output above for more information")
                return None
            else:
                return process
