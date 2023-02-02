"""Module to manage Odoo processes."""

import re
from functools import lru_cache
from pathlib import Path
from subprocess import CalledProcessError
from typing import (
    TYPE_CHECKING,
    Generator,
    List,
    Mapping,
    Optional,
)

from odev.common import bash, style
from odev.common.config import config
from odev.common.connectors import GithubConnector, GitWorktree
from odev.common.logging import logging
from odev.common.python import PythonEnv
from odev.common.signal_handling import capture_signals
from odev.common.version import OdooVersion


if TYPE_CHECKING:
    from odev.common.databases import PostgresDatabase


logger = logging.getLogger(__name__)


ODOO_PYTHON_VERSIONS: Mapping[int, str] = {
    16: "3.10",
    15: "3.8",
    14: "3.8",
    13: "3.7",
    12: "3.7",
    11: "3.7",
}


class OdooBinProcess:
    """Class to manage an odoo-bin process."""

    additional_addons_paths: List[Path] = []
    """List of additional addons paths to use when starting the Odoo process."""

    def __init__(self, database: "PostgresDatabase", venv: str = None):
        """Initialize the OdooBinProcess object."""
        self.database: PostgresDatabase = database
        """Database this process is for."""

        self.clone_repositories()
        self.repository: GithubConnector = GithubConnector("odoo/odoo")
        """Github repository of Odoo."""

        self.version: Optional[OdooVersion] = None
        """Version of Odoo running in this process."""

        if self.database.exists():
            with self.database:
                self.version = self.database.odoo_version()

        self.venv = PythonEnv(self.venv_path / (venv or "venv"), self._get_python_version())
        """Python virtual environment used by the Odoo installation."""

    def __repr__(self) -> str:
        return f"OdooBinProcess(database={self.database.name!r}, version={self.version!r}, venv={self.venv!r}, pid={self.pid()!r})"

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
        return self.odoo_path / "odoo-bin"

    @property
    def venv_path(self):
        """Path to the virtual environment of the Odoo installation."""
        with config:
            return Path(config.get("paths", "repositories")).parent / ".virtualenvs" / str(self.version)

    @lru_cache
    def _get_ps_process(self) -> Optional[str]:
        """Return the process currently running odoo, if any.
        Grep-ed `ps aux` output.
        """
        process = bash.execute(
            f"ps aux | grep -E 'odoo-bin\\s+(-d|--database)(\\s+|=){self.database.name}\\s*' || echo -n ''"
        )

        if process is not None:
            return process.stdout.decode()

        return None

    def _get_python_version(self) -> Optional[str]:
        """Return the Python version used by the current Odoo installation."""
        if self.version is None:
            return None

        return ODOO_PYTHON_VERSIONS.get(self.version.major, "2.7" if self.version.major < 11 else None)

    def _get_odoo_branch(self) -> str:
        """Return the branch of the current Odoo installation."""
        if self.version is None:
            return "master"

        return str(self.version)

    def pid(self) -> Optional[int]:
        """Return the process id of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return int(re.split(r"\s+", process)[1])

    def command(self) -> Optional[str]:
        """Return the command of the process of the current database if it is running."""
        process = self._get_ps_process()

        if not process:
            return None

        return " ".join(re.split(r"\s+", process)[10:])

    def rpc_port(self) -> Optional[int]:
        """Return the RPC port of the process of the current database if it is running."""
        command = self.command()

        if not command:
            return None

        match = re.search(r"(?:-p|--http-port)(?:\s+|=)([0-9]{1,5})", command)
        return int(match.group(1)) if match is not None else 8069

    def is_running(self) -> bool:
        """Return whether Odoo is currently running on the database."""
        return self.pid() is not None

    def kill(self, hard: bool = False):
        """Kill the process of the current database.

        :param hard: Send a SIGKILL instead of a SIGTERM to the running process.
        """
        pid = self.pid()

        if pid is not None:
            bash.execute(f"kill -{9 if hard else 2} {pid}")

    def run(self, args: List[str] = None, subcommand: str = None):
        """Run Odoo on the current database."""
        if self.is_running():
            raise RuntimeError("Odoo is already running on this database.")

        odoo_bin_args: List[str] = []
        odoo_bin_args.extend(["-d", self.database.name])
        odoo_bin_args.extend(["--addons-path", ",".join(path.as_posix() for path in self.addons_paths)])
        odoo_bin_args.extend(args or [])

        if subcommand is not None:
            odoo_bin_args.insert(0, subcommand)

        self.prepare_venv()
        self.update_worktrees()

        with capture_signals():
            logger.info(f"Running Odoo {self.version!s} on database {self.database.name!r} using command:")
            style.console.print(f"\n[{style.CYAN}]{self.odoobin_path} {' '.join(odoo_bin_args)}[/{style.CYAN}]\n")

            try:
                self.venv.run_script(self.odoobin_path, odoo_bin_args, stream=True)
            except CalledProcessError:
                style.console.print()
                logger.error("Odoo exited with an error, check the output above for more information")

    def prepare_venv(self):
        """Prepare the virtual environment of the Odoo installation."""
        if not self.venv.exists:
            self.venv.create_venv()

        for path in self.addons_requirements:
            if any(self.venv.missing_requirements(path)):
                self.venv.install_requirements(path)

    def update_worktrees(self):
        """Update the worktrees of the Odoo repositories."""
        for repository in self.odoo_repositories:
            repository.prune_worktrees()
            worktree = repository.get_worktree(self._get_odoo_branch())
            requirements = repository.modified_worktrees_requirements([worktree])
            repository.pull_worktrees([worktree])
            repository.fetch_worktrees([worktree])

            for requirement in requirements:
                self.venv.install_requirements(requirement)

    def clone_repositories(self):
        """Clone the missing Odoo repositories."""
        for repo in self.odoo_repositories:
            repo.clone()

            if not repo.branch == "master":
                repo.checkout("master")

    @property
    def odoo_repositories(self) -> Generator[GithubConnector, None, None]:
        """Return the list of Odoo repositories the current version."""
        repo_names: List[str] = ["odoo", "design-themes"]

        with self.database:
            if self.database.odoo_edition() == "enterprise":
                repo_names.insert(1, "enterprise")

        for repo_name in repo_names:
            yield GithubConnector(f"odoo/{repo_name}")

    @property
    def odoo_worktrees(self) -> Generator[GitWorktree, None, None]:
        """Return the list of Odoo worktrees the current version."""
        for repo in self.odoo_repositories:
            yield repo.get_worktree(self._get_odoo_branch())

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
            for path in self.addons_paths + [worktree.path for worktree in self.odoo_worktrees]
        )
        return (path for glob in globs for path in glob)

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
