"""Upgrades a local Odoo database."""
import asyncio
import os
import re
import subprocess
import sys
import tempfile
from argparse import REMAINDER, Namespace
from asyncio.subprocess import PIPE, STDOUT, Process
from collections import defaultdict
from getpass import getuser
from pathlib import Path
from typing import (
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Union,
)

from blessed.sequences import Sequence as TermSequence
from packaging.version import Version

from odev.exceptions.odoo import RunningOdooDatabase
from odev.structures.commands import LocalDatabaseCommand
from odev.utils import logging
from odev.utils.odoo import branch_from_version, parse_odoo_version, prepare_odoobin
from odev.utils.psql import PSQL
from odev.utils.signal import capture_signals
from odev.utils.spinner import SpinnerBar


_logger = logging.getLogger(__name__)


StrOrPath = Union[str, Path]


UPGRADE_STEPS: Sequence[str] = [
    "6.1",
    "7.0",
    "8.0",
    "9.0",
    "10.0",
    "11.0",
    "12.0",
    "saas~12.3",
    "13.0",
    "14.0",
    "15.0",
    "16.0",
]

# upgrade-docker/upgrade.py runner script that patches hardcoded paths with prepared ones,
# this way we can run the script outside a docker container and without using sudo+chroot
RUNNER_SCRIPT: str = """
import os
import re
import sys
from types import ModuleType
from typing import List, Any, Union, Optional


# restore stdin to terminal
sys.stdin.close()
sys.stdin = open(os.ctermid())


# --- START PATCH subprocess.Popen to set stdin to tty --- #

from subprocess import Popen

Popen___init____orig = Popen.__init__


def Popen___init____patched(*args, stdin=None, **kwargs):
    if stdin is None:
        stdin = sys.stdin
    Popen___init____orig(*args, stdin=stdin, **kwargs)


Popen.__init__ = Popen___init____patched

# --- END PATCH --- #


home_path: str = os.environ["UPGRADE_HOME_PATH"]  # required

upgrade_docker_path: str = os.path.join(
    home_path, "src/upgrade-platform/upgrade-docker"
)


def patch_paths(paths: Union[str, List[str]]) -> Union[str, List[str]]:
    is_string: bool = isinstance(paths, str)
    if is_string:
        paths = [paths]
    paths = [re.sub(r"^(?:/home/odoo|~)", home_path, path) for path in paths]
    return paths[0] if is_string else paths


import util, upgrade

module: ModuleType
attr: str
for module in (util, upgrade):
    for attr in dir(module):
        value: Any = getattr(module, attr)
        if isinstance(value, str) or (
            isinstance(value, list) and value and isinstance(value[0], str)
        ):
            setattr(module, attr, patch_paths(value))


# --- START PATCH util.run_command to remove None args (eg. no PGPASSWORD set) --- #

run_command__orig = util.run_command


def run_command__patched(command: Any, *args, **kwargs):
    if isinstance(command, (list, tuple)):
        command: List[Optional[str]] = list(command)
        while None in command:
            i: int = command.index(None)
            if i == 0 or not command[i - 1].startswith("-"):
                raise RuntimeError(f"Cannot patch None value in command: {command}")
            command = command[: i - 1] + command[i + 1 :]

    run_command__orig(command, *args, **kwargs)


util.run_command = run_command__patched

# --- END PATCH --- #


upgrade.main()
"""


class UpgradeCommand(LocalDatabaseCommand):
    """
    Upgrade a local Odoo database, running migration scripts between each major versions.
    """

    name = "upgrade"
    arguments = [
        {
            "aliases": ["target"],
            "help": "Odoo version to target; must match an Odoo community branch",
        },
        {
            "aliases": ["args"],
            "nargs": REMAINDER,
            "help": """
                Additional arguments to pass to upgrade.py; Check the code at
                https://github.com/odoo/upgrade-platform/blob/master/upgrade-docker/upgrade.py#L355
                for the list of available arguments.
                (N.B. -d and -t are already provided by odev)
            """,
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.target: str = args.target
        self.additional_args: Sequence[str] = args.args or []

    @staticmethod
    def get_required_versions(version_from: str, version_to: str) -> Sequence[str]:
        """
        Returns a sequence of the required Odoo versions as strings needed to upgrade
        from ``version_from`` to ``version_to``. Will always include ``version_from``.
        """
        version_from_parsed: Version = parse_odoo_version(version_from)
        version_to_parsed: Version = parse_odoo_version(version_to)
        version: str
        required_versions: List[str] = [
            version
            for version in UPGRADE_STEPS
            if version_from_parsed <= parse_odoo_version(version) <= version_to_parsed
        ]
        if version_from not in required_versions:
            required_versions.insert(0, version_from)
        return required_versions

    def prepare_repos(self, version_before: str, version_target: str) -> None:
        """
        Ensures the required Odoo repositories are cloned (and updated) for the versions
        needed for the upgrade.
        """
        # TODO: merge --ff-only, do not pull
        repos_root_odev: str = self.config["odev"].get("paths", "odoo")
        version: str
        for version in self.get_required_versions(version_before, version_target):
            prepare_odoobin(
                repos_root_odev,
                version,
                upgrade=(version == version_before),
                venv=False,
            )

    @staticmethod
    def parse_dockerfile_venv(dockerfile: StrOrPath) -> Mapping[str, Sequence[str]]:
        """
        Parses the ``upgrade-docker`` Dockerfile to extract the commands required
        to build the virtualenvs needed for the upgrade process, and returns them
        as a mapping of Odoo versions strings to commands strings sequences.
        """
        dockerfile_run_lines: List[str] = []
        with open(dockerfile) as fp:
            docker_instruction: Optional[str] = None
            line_continues: bool = False
            current_run_lines: List[str] = []
            file_line: str
            for file_line in fp.readlines():
                # skip empty or comment lines
                if not file_line.strip() or re.search(r"^\s*#", file_line):
                    continue

                line: str = file_line.strip()

                if not line_continues:
                    instruction_match = re.search(r"^(\w+\b)\s+(.*)", line)
                    if instruction_match:
                        docker_instruction = instruction_match.group(1).upper()
                        line = instruction_match.group(2).strip()

                in_run_istruction: bool = docker_instruction == "RUN"

                line_continues_match = re.search(r"^(.*)\s*\\$", line)
                line_continues = bool(line_continues_match)
                if line_continues_match:
                    line = line_continues_match.group(1).strip()

                if in_run_istruction:
                    current_run_lines.append(line)

                if not in_run_istruction or not line_continues:
                    if current_run_lines:
                        dockerfile_run_lines.append(" ".join(current_run_lines))
                        current_run_lines = []

        venv_commands: MutableMapping[str, List[str]] = defaultdict(list)
        run_line: str
        for run_line in dockerfile_run_lines:
            for commandline in re.split(r"\s*(?:&&|;)\s*", run_line.strip()):
                venv_match = re.search(r"venvs/([\d.]+)", commandline)
                if venv_match:
                    venv_version: str = venv_match.group(1)
                    venv_commands[venv_version].append(commandline.strip())

        return venv_commands

    def prepare_venvs(
        self,
        home_path: StrOrPath,
        odev_upgrade_venvs_path: StrOrPath,
        upgrade_docker_path: StrOrPath,
    ) -> None:
        """
        Prepares the virtualenvs needed for the upgrade process.
        """
        pbar: SpinnerBar

        # TODO: refactor into a global util function?
        async def run_subcommand_async(cmd: str) -> int:
            nonlocal pbar
            poll_interval: float = 0.05
            stdout: str = ""

            proc: Process = await asyncio.create_subprocess_shell(cmd, stdout=PIPE, stderr=STDOUT)
            assert proc.stdout is not None
            pbar.message = cmd

            for _ in pbar.loop(poll_interval):
                try:
                    line: str = (await asyncio.wait_for(proc.stdout.readline(), poll_interval)).decode()
                except asyncio.TimeoutError:
                    pass
                else:
                    stdout += line
                    msg: str = TermSequence(line, logging.term).strip_seqs()
                    if msg.strip():
                        pbar.message = msg.strip()

                if proc.returncode is not None:
                    break

            if proc.returncode != 0:
                _logger.error(f"Error in subprocess, output:\n{stdout}")
                raise subprocess.CalledProcessError(proc.returncode or 1, command)

            return proc.returncode

        home_path = Path(home_path)

        odev_upgrade_venvs_path = Path(odev_upgrade_venvs_path)
        venvs_path: Path = home_path / ".odoo-venvs"
        if not os.path.exists(odev_upgrade_venvs_path):
            os.makedirs(odev_upgrade_venvs_path)
        os.symlink(odev_upgrade_venvs_path.resolve(), venvs_path)

        venv_commands: Mapping[str, Sequence[str]] = self.parse_dockerfile_venv(
            Path(upgrade_docker_path) / "Dockerfile"
        )

        venv_version: str
        commands: Sequence[str]
        last_venv_version: Optional[str] = None
        with SpinnerBar() as pbar:
            for venv_version, commands in reversed(list(venv_commands.items())):
                venv_odoo_versions: str = f">={venv_version}" + (f",<{last_venv_version}" if last_venv_version else "")
                _logger.info(f"Setting up upgrade venv for Odoo versions {venv_odoo_versions}")
                command: str
                for command in commands:
                    # replace references to /home/odoo path to the temp home_path
                    command = re.sub(r"/home/odoo|~", str(home_path), command)
                    # replace paths pointing to the venvs with their real path, to avoid temp paths being stored
                    command = re.sub(re.escape(str(venvs_path)), str(odev_upgrade_venvs_path), command)
                    with capture_signals():
                        asyncio.run(run_subcommand_async(command))
                last_venv_version = venv_version

    def setup_fs_tree(
        self,
        home_path: StrOrPath,
        version_before: str,
        version_target: str,
    ) -> None:
        """
        Prepares the filesystem directories and files as expected by the upgrade-platform
        scripts with ``home_path`` as the would-be ``/home/odoo`` path (which will then
        be patched in scripts), mostly by symlinking odev's clones of Odoo repos.
        """

        def symlink(src: StrOrPath, dest: StrOrPath, resolve: bool = True):
            os.symlink(Path(src).resolve() if resolve else src, dest)

        _logger.info(f"Preparing filesystem for upgrade at {home_path}")

        odev_repos_root: Path = Path(self.config["odev"].get("paths", "odoo"))

        home_path = Path(home_path)
        src_path: Path = home_path / "src"

        versioned_paths: Mapping[str, str] = {
            "odoo": "odoo",
            "enterprise": "enterprise",
            "design-themes": "themes",
        }

        for link_src, link_dest in versioned_paths.items():
            os.makedirs(src_path / link_dest)
            for version in self.get_required_versions(version_before, version_target):
                branch: str = branch_from_version(version)
                full_src: Path = odev_repos_root / branch / link_src
                full_dest: Path = src_path / link_dest / branch
                symlink(full_src, full_dest)

        repo: str
        for repo in ("upgrade", "upgrade-specific", "upgrade-platform"):
            symlink(odev_repos_root / repo, src_path / repo)

        maintenance_path: Path = home_path.resolve() / ".odoo-maintenance"
        symlink(src_path / "upgrade", maintenance_path)
        odoo_name: str
        for odoo_name in ("odoo", "openerp"):
            odoo_base_dir: Path
            for odoo_base_dir in src_path.glob(f"odoo/*/{odoo_name}/addons/base"):
                base_maintenance_symlink = odoo_base_dir / "maintenance"
                if base_maintenance_symlink.is_symlink():
                    base_maintenance_symlink.unlink()
                symlink(maintenance_path, base_maintenance_symlink, resolve=False)

        upgrade_docker_path: Path = src_path / "upgrade-platform/upgrade-docker"

        odev_upgrade_venvs_path: Path = odev_repos_root / "venvs_upgrade"
        self.prepare_venvs(home_path, odev_upgrade_venvs_path, upgrade_docker_path)

        os.makedirs(home_path / "data")

        bin_path: Path = home_path / "bin"
        os.makedirs(bin_path)
        symlink(upgrade_docker_path / "main.py", bin_path / "main.py")
        symlink(upgrade_docker_path / "start.py", bin_path / "start.py")
        symlink(upgrade_docker_path / "upgrade.py", bin_path / "upgrade.py")

    def run(self):
        """
        Upgrade a local Odoo database.
        """

        self.check_database()

        if self.db_runs():
            raise RunningOdooDatabase(f"Database {self.database} is already running, please shut it down first")

        before_version: str = self.db_version_clean()

        if parse_odoo_version(self.target) == parse_odoo_version(before_version):
            _logger.warning(f"Database {self.database} is already at version {self.target}, nothing to upgrade")
            return 0
        elif parse_odoo_version(self.target) <= parse_odoo_version(before_version):
            _logger.error(f"Database {self.database} is at a newer version than {self.target}, cannot downgrade")
            return 1

        # TODO: create a template/backup? add an option for that?

        self.prepare_repos(before_version, self.target)

        with tempfile.TemporaryDirectory(prefix="odev_upgrade_") as upgrade_home:
            self.setup_fs_tree(upgrade_home, before_version, self.target)

            with capture_signals():
                env: MutableMapping[str, str] = dict(os.environ, UPGRADE_HOME_PATH=os.path.abspath(upgrade_home))
                with PSQL() as psql:
                    assert psql.connection is not None
                    pg_params: Mapping[str, str] = psql.connection.get_dsn_parameters()
                env.setdefault("PGUSER", pg_params.get("user", getuser()))
                if pg_params.get("password"):
                    env.setdefault("PGPASSWORD", pg_params["password"] or "")
                subprocess.run(
                    [
                        *(sys.executable, "-"),
                        *("-d", self.database),
                        *("-t", self.target),
                        *self.additional_args,
                    ],
                    cwd=os.path.join(upgrade_home, "src/upgrade-platform/upgrade-docker"),
                    env=env,
                    input=RUNNER_SCRIPT,
                    text=True,
                    check=True,
                )

            # TODO: copy logs/state before temp dir deletion

        version_after: str = self.db_version_clean()
        self.config["databases"].set(self.database, "version_clean", version_after)
        self.config["databases"].set(self.database, "version", self.db_base_version())

        if version_after != self.target:
            _logger.warning(
                f"Upgraded version of {self.database} is {version_after} " f"instead of the requested {self.target}!"
            )
        else:
            _logger.success(f"Successfully upgraded {self.database} [{before_version} -> {version_after}]")
        return 0
