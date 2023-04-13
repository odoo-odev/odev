"""Module to manage Odoo processes."""

import re
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import (
    TYPE_CHECKING,
    Callable,
    Generator,
    List,
    Mapping,
    Optional,
    Sequence,
)

from odev.common import bash
from odev.common.connectors import GitConnector, GitWorktree
from odev.common.console import Colors
from odev.common.databases import Branch, Repository
from odev.common.logging import LOG_LEVEL, logging
from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.progress import spinner
from odev.common.python import PythonEnv
from odev.common.signal_handling import capture_signals
from odev.common.version import OdooVersion


if TYPE_CHECKING:
    from odev.common.databases import LocalDatabase


__all__ = ["OdooBinProcess", "ODOO_PYTHON_VERSIONS"]


logger = logging.getLogger(__name__)


ODOO_COMMUNITY_REPOSITORIES: List[str] = [
    "odoo/odoo",
    "odoo/design-themes",
]

ODOO_ENTERPRISE_REPOSITORIES: List[str] = ["odoo/enterprise"]

ODOO_PYTHON_VERSIONS: Mapping[int, str] = {
    16: "3.10",
    15: "3.8",
    14: "3.8",
    13: "3.7",
    12: "3.7",
    11: "3.7",
}


class OdooBinProcess(OdevFrameworkMixin):
    """Class to manage an odoo-bin process."""

    _additional_addons_paths: List[Path] = []
    """List of additional addons paths to use when starting the Odoo process."""

    _venv: Optional[PythonEnv] = None
    """Cached python virtual environment used by the Odoo installation."""

    _force_enterprise: bool = False
    """Force using the enterprise version of Odoo."""

    def __init__(self, database: "LocalDatabase", venv: str = None, version: OdooVersion = None):
        """Initialize the OdooBinProcess object."""
        super().__init__()

        self.database: LocalDatabase = database
        """Database this process is for."""

        self._version: Optional[OdooVersion] = version
        """Force the version of Odoo when running the process."""

        self._venv_name: str = venv or "venv"
        """Name of the virtual environment to use."""

        self.clone_repositories()
        self.repository: GitConnector = GitConnector("odoo/odoo")
        """Github repository of Odoo."""

    def __repr__(self) -> str:
        return f"OdooBinProcess(database={self.database.name!r}, version={self.version!r}, venv={self.venv!r}, pid={self.pid!r})"

    @property
    def venv(self) -> PythonEnv:
        """Python virtual environment used by the Odoo installation."""
        if self._venv is None:
            self._venv = PythonEnv(self.venv_path / self._venv_name, self._get_python_version())

        return self._venv

    @property
    def version(self) -> Optional[OdooVersion]:
        """Version of Odoo running in this process."""
        if self._version is not None:
            return self._version

        if not self.database.exists:
            return None

        with self.database:
            return self.database.version

    @property
    def odoo_path(self) -> Path:
        """Path to the Odoo installation."""
        odoo_branch = self._get_odoo_branch()

        if odoo_branch is None:
            return self.repository.path

        worktree = self.repository.get_worktree(odoo_branch)
        assert worktree is not None
        return worktree.path

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
        return self.config.paths.repositories.parent / ".virtualenvs" / str(self.version)

    @property
    def pid(self) -> Optional[int]:
        """Return the process id of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return int(re.split(r"\s+", process)[1])

    @property
    def command(self) -> Optional[str]:
        """Return the command of the process of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return " ".join(re.split(r"\s+", process)[10:])

    @property
    def rpc_port(self) -> Optional[int]:
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
        repo_names: List[str] = [*ODOO_COMMUNITY_REPOSITORIES]

        with self.database:
            if self.database.edition == "enterprise" or self._force_enterprise:
                for repo_name in ODOO_ENTERPRISE_REPOSITORIES:
                    repo_names.insert(1, repo_name)

        for repo_name in repo_names:
            yield GitConnector(repo_name)

    @property
    def additional_addons_paths(self) -> List[Path]:
        """Return the list of additional addons paths."""
        return self._additional_addons_paths

    @additional_addons_paths.setter
    def additional_addons_paths(self, value: List[Path]):
        """Set the list of additional addons paths."""
        self._additional_addons_paths = value
        self.set_database_repository()

    @property
    def additional_repositories(self) -> Generator[GitConnector, None, None]:
        """Return the list of additional repositories linked to this database."""
        for path in self.additional_addons_paths:
            if path.is_dir():
                yield GitConnector(f"{path.parent.name}/{path.name}")

    @property
    def odoo_worktrees(self) -> Generator[GitWorktree, None, None]:
        """Return the list of Odoo worktrees the current version."""
        branch = self._get_odoo_branch()

        for repo in self.odoo_repositories:
            yield repo.get_worktree(branch)

    @property
    def odoo_addons_paths(self) -> List[Path]:
        """Return the list of Odoo addons paths."""
        return [
            worktree.path / addon
            for addon in ["", "addons", "odoo/addons", "openerp/addons"]
            for worktree in self.odoo_worktrees
            if self.check_addons_path(worktree.path / addon)
        ]

    @property
    def addons_paths(self) -> List[Path]:
        """Return the list of addons paths."""
        return [path for path in self.odoo_addons_paths + self.additional_addons_paths if self.check_addons_path(path)]

    @property
    def addons_requirements(self) -> Generator[Path, None, None]:
        """Return the list of addons requirements files."""
        globs = (
            path.glob("requirements.txt")
            for path in (
                self.addons_paths
                + [Path(__file__).parents[1] / "static"]
                + [worktree.path for worktree in self.odoo_worktrees]
            )
        )
        return (path for glob in globs for path in glob)

    def with_version(self, version: OdooVersion = None) -> "OdooBinProcess":
        """Return the OdooBinProcess instance with the given version forced."""
        self._version = version
        self._venv = None
        return self

    @lru_cache
    def _get_ps_process(self) -> Optional[str]:
        """Return the process currently running odoo, if any.
        Grep-ed `ps aux` output.
        """
        process = bash.execute(
            f"ps aux | grep -E 'odoo-bin\\s+(-d|--database)(\\s+|=){self.database.name}(\\s+|$)' || echo -n ''"
        )

        if process is not None:
            return process.stdout.decode()

        return None

    def _get_python_version(self) -> Optional[str]:
        """Return the Python version used by the current Odoo installation."""
        if self.version is None:
            return None

        if self.version == OdooVersion("master"):
            return ODOO_PYTHON_VERSIONS.get(max(ODOO_PYTHON_VERSIONS.keys()), None)

        return ODOO_PYTHON_VERSIONS.get(self.version.major, "2.7" if self.version.major < 11 else None)

    def _get_odoo_branch(self) -> str:
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

    def prepare_odoobin_args(self, args: List[str] = None, subcommand: str = None) -> List[str]:
        """Prepare the arguments to pass to odoo-bin.

        :param args: Additional arguments to pass to odoo-bin.
        :param subcommand: Subcommand to pass to odoo-bin.
        :return: List of arguments to pass to odoo-bin.
        :rtype: List[str]
        """

        odoo_bin_args: List[str] = []
        odoo_bin_args.extend(["-d", self.database.name])
        odoo_bin_args.extend(["--addons-path", ",".join(path.as_posix() for path in self.addons_paths)])
        odoo_bin_args.extend(["--log-level", LOG_LEVEL.lower()])
        odoo_bin_args.extend(args or [])

        if subcommand is not None:
            odoo_bin_args.insert(0, subcommand)

        return odoo_bin_args

    def prepare_odoobin(self):
        """Prepare the odoo-bin executable and ensure all dependencies are installed."""
        self.prepare_npm()
        self.update_worktrees()
        self.prepare_venv()

    def run(
        self,
        args: List[str] = None,
        subcommand: str = None,
        stream: bool = True,
        progress: Callable[[str], None] = None,
    ) -> Optional[CompletedProcess]:
        """Run Odoo on the current database.

        :param args: Additional arguments to pass to odoo-bin.
        :param subcommand: Subcommand to pass to odoo-bin.
        :param stream: Whether to stream the output of the process.
        :param dry: Whether to only print the command that would be executed without running it.
        :param progress: Callback to call on each line outputted by the process. Ignored if `stream` is False.
        :return: The return result of the process after completion.
        :rtype: subprocess.CompletedProcess
        """
        if self.is_running and subcommand is None:
            raise RuntimeError("Odoo is already running on this database")

        with spinner(f"Preparing Odoo {self.version!s} for database {self.database.name!r}"):
            self.prepare_odoobin()

        if stream and progress is not None and self.addons_contain_debugger():
            logger.warning("Addons contain a call to a debugger, streaming of Odoo logs is deactivated")
            progress = None

        with capture_signals():
            odoo_command = f"odoo-bin {subcommand}" if subcommand is not None else "odoo-bin"
            info_message = f"Running {odoo_command!r} in version {self.version!s} on database {self.database.name!r}"
            odoobin_args = self.prepare_odoobin_args(args, subcommand)

            logger.info(f"{info_message} using command:")
            self.console.print(
                f"\n[{Colors.CYAN}]{self.venv.python} {self.odoobin_path} {' '.join(odoobin_args)}[/{Colors.CYAN}]\n",
                soft_wrap=True,
            )

            try:
                with spinner(info_message) if not stream else nullcontext():
                    process = self.venv.run_script(self.odoobin_path, odoobin_args, stream=stream, progress=progress)
            except CalledProcessError as error:
                if not stream:
                    self.console.print(error.stderr.decode())

                return logger.error("Odoo exited with an error, check the output above for more information")
            else:
                return process

    def prepare_npm(self):
        """Prepare the packages of the Odoo installation."""
        try:
            logger.debug("Verifying NPM installation")
            bash.execute("npm --version")
        except Exception:
            raise RuntimeError("NPM is not installed, please install it first")

        packages = ["rtlcss"]

        if self.version.major <= 10:
            packages.extend(["less", "less-plugin-clean-css"])

        missing = list(self.missing_npm_packages(packages))

        if any(missing):
            bash.execute(f"cd {self.odoo_path} && npm install {' '.join(missing)}")

    def missing_npm_packages(self, packages: Sequence[str]) -> Generator[str, None, None]:
        """Check whether the given NPM packages are installed in the version folder of Odoo."""
        installed_packages = bash.execute(f"cd {self.odoo_path} && npm list").stdout.decode()

        for package in packages:
            if f" {package}" not in installed_packages:
                yield package

    def prepare_venv(self):
        """Prepare the virtual environment of the Odoo installation."""
        if not self.venv.exists:
            self.venv.create_venv()

        for path in self.addons_requirements:
            if any(self.venv.missing_requirements(path)):
                self.venv.install_requirements(path)

        if self.version.major < 10 and not self.version.master:
            self.venv.install_packages(["psycopg2==2.7.3.1"])

    def update_worktrees(self):
        """Update the worktrees of the Odoo repositories."""
        for repository in self.odoo_repositories:
            repository.prune_worktrees()
            worktree = repository.get_worktree(self._get_odoo_branch())
            repository.pull_worktrees([worktree])
            repository.fetch_worktrees([worktree])

    def clone_repositories(self):
        """Clone the missing Odoo repositories."""
        for repo in self.odoo_repositories:
            repo.clone()

            if not repo.branch == "master":
                repo.checkout("master")

    def check_addons_path(self, path: Path) -> bool:
        """Return whether the given path is a valid Odoo addons path.

        :param path: Path to check.
        :return: True if the path is a valid Odoo addons path, False otherwise.
        :rtype: bool
        """
        if not path.is_dir():
            return False

        globs = (path.glob(f"*/__{manifest}__.py") for manifest in ["manifest", "openerp"])
        return path.is_dir() and any(manifest for glob in globs for manifest in glob)

    def addons_contain_debugger(self):
        """Check if the source code has a debugger called."""
        for addon in self.addons_paths:
            for python_file in addon.glob("**/*.py"):
                with python_file.open() as file:
                    for line in file.readlines():
                        if re.search(r"(i?pu?db)\.set_trace\(", line.split("#", 1)[0]):
                            return True

    def set_database_repository(self):
        """Link the database to the first repository in additional addons-paths."""
        repository = next(self.additional_repositories, None)

        if repository is None:
            return

        info = self.database.store.databases.get(self.database)

        if info is not None and info.repository == repository.name:
            return

        self.database.repository = Repository(repository._repository, repository._organization)
        self.database.branch = Branch(repository.branch, self.database.repository)
