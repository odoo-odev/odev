"""Self update Odev by pulling latest changes from the git repository."""

import inspect
import os
import pkgutil
import re
import sys
from datetime import datetime, timedelta
from importlib.machinery import FileFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    List,
    MutableMapping,
)

from git import Remote, Repo
from packaging import version

from odev._version import __version__
from odev.common import bash, progress, prompt, style
from odev.common.config import ConfigManager
from odev.common.errors import CommandError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.python import PythonEnv
from odev.common.store import DataStore
from odev.constants import DEFAULT_DATETIME_FORMAT


if TYPE_CHECKING:
    from rich.console import Console

    from odev.common.commands.base import CommandType


logger = logging.getLogger(__name__)


class Odev:
    """Main framework class."""

    version: ClassVar[str] = __version__
    """Odev version."""

    path: ClassVar[Path] = Path(__file__).parents[2]
    """Local path to the odev repository."""

    config: ClassVar["ConfigManager"] = None
    """Odev configuration."""

    store: ClassVar["DataStore"] = None
    """Odev data storage."""

    commands: ClassVar[MutableMapping[str, "CommandType"]] = {}
    """Collection of existing and loaded commands."""

    executable: ClassVar[Path] = Path(sys.argv[0])
    """Path to the current executable."""

    def __init__(self):
        logger.debug(f"Starting odev version {self.version}")
        if self.__class__.config is None:
            self.__class__.config = ConfigManager(self.name)

        if self.__class__.store is None:
            self.__class__.store = DataStore(self.name)

        self.repo: Repo = Repo(self.path)
        """Local git repository."""

        with progress.spinner(f"Checking for updates to odev {self.version}"):
            if self.update():
                self.restart()

        with progress.spinner("Loading commands"):
            self.register_commands()

    def __repr__(self) -> str:
        return f"Odev(version={self.version})"

    @property
    def name(self) -> str:
        """Name of the framework."""
        return "odev"

    @property
    def _console(self) -> "Console":
        """Rich console instance to display information to users."""
        return style.console

    @property
    def commands_path(self) -> Path:
        """Local path to the commands directory."""
        return self.path / "odev" / "commands"

    @property
    def upgrades_path(self) -> Path:
        """Local path to the upgrades directory."""
        return self.path / "odev" / "upgrades"

    @property
    def setup_path(self) -> Path:
        """Local path to the setup directory."""
        return self.path / "odev" / "setup"

    @property
    def dumps_path(self) -> Path:
        """Local path to the directory where database dumps are stored."""
        with self.config:
            return Path(self.config.get("paths", "repositories")).parent / "dumps"

    def update(self) -> bool:
        """
        Check for updates in the odev repository and download them if necessary.

        :param config: Odev configuration
        :return: Whether updates were pulled and installed
        :rtype: bool
        """
        if not sys.stdout.isatty() or not sys.stdin.isatty():
            return False

        if not self.__date_check_interval() or not self.__git_branch_behind():
            bash.detached(f"cd {self.path} && git fetch")
            return False

        if not self.__update_prompt():
            return False

        logger.debug(
            f"Pulling latest changes from odev repository on branch {self.repo.active_branch.tracking_branch()}"
        )
        self.config.set("update", "date", datetime.now().strftime(DEFAULT_DATETIME_FORMAT))
        install_requirements = self.__requirements_changed()
        self.repo.remotes.origin.pull()

        if install_requirements:
            logger.debug("Installing new odev package requirements")
            PythonEnv().install_requirements(self.path)

        self.upgrade()

        return True

    def restart(self) -> None:
        """Restart the current process with the latest version of odev."""
        logger.debug("Restarting odev")
        os.execv(self.executable.as_posix(), [*sys.argv, f"--log-level={LOG_LEVEL}"])

    def check_upgrade(self) -> bool:
        """Check whether the current version of odev is the latest available version.

        :return: Whether the current version is the latest available version
        :rtype: bool
        """
        logger.debug("Checking for existing odev upgrades")
        return version.parse(self.version) > version.parse(self.__latest_version())

    def upgrade(self) -> None:
        """Upgrade the current version of odev."""
        if not self.check_upgrade():
            return

        current_version = self.__latest_version()

        logger.debug(f"Upgrading odev from version {current_version} to {self.version}")
        scripts = self.__list_upgrade_scripts()

        for script in scripts:
            logger.debug(f"Running upgrade script [{current_version} -> {script.parent.name}]")
            self.__run_upgrade_script(script)

        self.config.set("update", "version", self.version)

    def import_commands(self) -> List["CommandType"]:
        """Import all commands from the commands directory.

        :return: List of imported command classes
        :rtype: List[CommandType]
        """
        command_dirs = [
            path for path in self.commands_path.iterdir() if path.is_dir() and not path.name.startswith("_")
        ]
        command_modules = pkgutil.iter_modules([d.as_posix() for d in command_dirs])
        command_classes: List["CommandType"] = []

        for module_info in command_modules:
            assert isinstance(module_info.module_finder, FileFinder)
            module_path = Path(module_info.module_finder.path) / f"{module_info.name}.py"
            spec = spec_from_file_location(module_path.stem, module_path.as_posix())
            assert spec is not None and spec.loader is not None
            command_module: ModuleType = module_from_spec(spec)
            spec.loader.exec_module(command_module)
            command_classes.extend(command[1] for command in inspect.getmembers(command_module, self.__filter_commands))

        return command_classes

    def register_commands(self) -> None:
        """Register all commands from the commands directory."""
        for command_class in self.import_commands():
            logger.debug(f"Registering command {command_class.name!r}")
            command_names = [command_class.name] + (list(command_class.aliases) or [])

            if any(name in command_names for name in self.commands.keys()):
                raise ValueError(f"Another command {command_class.name!r} is already registered")

            command_class.prepare_command(self)
            self.commands.update({name: command_class for name in command_names})

    def parse_arguments(self, command_cls: "CommandType", *args):
        """Parse arguments for a command.

        :param command_cls: Command class to parse arguments for
        :param args: Arguments to parse
        :return: Parsed arguments
        """
        try:
            logger.debug(f"Parsing command arguments '{' '.join(args)}'")
            arguments = command_cls.parse_arguments(args)
        except SystemExit as exception:
            raise command_cls.error(None, str(exception))
        return arguments

    def run_command(self, name: str, *cli_args: str, history: bool = False) -> None:
        """Run a command with the given arguments.

        :param name: Name of the command to run
        :param cli_args: Arguments to pass to the command
        :param history: Whether to add the command to the command history.
        """
        command_cls = self.commands.get(name)

        if command_cls is None:
            return logger.error(f"Command {name!r} not found")

        command = None  # Avoid UnboundLocalError during cleanup

        try:
            arguments = self.parse_arguments(command_cls, *cli_args)
            command = command_cls(arguments)
            command.argv = " ".join(cli_args)

            logger.debug(f"Dispatching {command!r}")
            command.run()
        except CommandError as exception:
            logger.error(str(exception))
        else:
            if history:
                self.store.history.set(command)
        finally:
            if command is not None:
                command.cleanup()

    def dispatch(self) -> None:
        """Handle commands and arguments as received from the terminal."""
        argv = sys.argv[1:]

        if (
            not len(argv)
            or (
                len(argv) >= 2
                and any(arg in filter(lambda a: a.startswith("-"), self.commands.get("help").aliases) for arg in argv)
            )
            or argv[0].startswith("-")
        ):
            logger.debug("Help argument or no command provided, falling back to help command")
            argv = ["help", *argv]

        self.run_command(argv[0], *argv[1:], history=True)

    # --- Private methods ------------------------------------------------------

    def __filter_commands(self, attribute: Any) -> bool:
        """Filter module attributes to extract commands.

        :param attribute: Module attribute
        :return: Whether the module attribute is a command
        :rtype: bool
        """
        from odev.common.commands.base import Command

        return inspect.isclass(attribute) and issubclass(attribute, Command) and not attribute.is_abstract()

    def __git_branch_behind(self) -> bool:
        """Assess whether the current branch is behind the remote tracking branch.

        :param repo: Git repository
        :param branch: Branch to check
        :return: Whether the branch is behind the remote tracking branch
        :rtype: bool
        """
        remote_branch = self.repo.active_branch.tracking_branch()

        if remote_branch is None:
            return False

        remote: Remote = self.repo.remotes[remote_branch.remote_name]
        rev_list: str = self.repo.git.rev_list("--left-right", "--count", f"{remote.name}...HEAD")
        commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split("\t")]
        message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
        message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"

        if commits_behind and commits_ahead:
            logger.debug(f"Odev is {message_behind} and {message_ahead} {remote.name}")
        elif commits_behind:
            logger.debug(f"Odev is {message_behind} {remote.name}")
        elif commits_ahead:
            logger.debug(f"Odev is {message_ahead} {remote.name}")
        else:
            logger.debug(f"Odev is up-to-date with {remote.name}")

        if commits_ahead:
            logger.debug("Running in development mode (no self-update)")
            return False

        return bool(commits_behind)

    def __requirements_changed(self) -> bool:
        """Assess whether the requirements.txt file was modified.

        :param repo: Git repository
        :return: Whether the requirements.txt file has changed
        :rtype: bool
        """
        requirements_file = self.path / "requirements.txt"
        diff = self.repo.git.diff("--name-only", "HEAD", requirements_file).strip()

        if diff == requirements_file.as_posix():
            logger.debug("Odev requirements have changed since last version")

        return bool(diff)

    def __date_check_interval(self) -> bool:
        """Check whether the last check date is older than today minus the check interval.

        :param config: Odev configuration
        :return: Whether the last check date is older than today minus the check interval
        :rtype: bool
        """
        default_date = (datetime.today() - timedelta(days=1)).strftime(DEFAULT_DATETIME_FORMAT)
        check_date = self.config.get("update", "date", default_date)
        check_interval = int(self.config.get("update", "interval", 1))
        check_diff = (datetime.today() - datetime.strptime(check_date, DEFAULT_DATETIME_FORMAT)).days
        return check_diff >= check_interval

    def __update_prompt(self) -> bool:
        """Prompt the user to update odev if a new version is available.

        :param config: Odev configuration
        :return: Whether the user wants to update odev
        :rtype: bool
        """
        update_mode = self.config.get("update", "mode", "ask")
        assert update_mode in ("ask", "always", "never")

        if update_mode == "ask":
            return prompt.confirm("An update is available for odev, do you want to download it now?")

        return update_mode == "always"

    def __latest_version(self) -> str:
        """Get the latest version of odev from the config file.

        :return: Latest version of odev
        :rtype: str
        """
        return self.config.get("update", "version", self.config.get("odev", "version", self.version))

    def __validate_upgrade_script(self, script: Path) -> bool:
        """Validate the upgrade script's version to check whether it should be run.

        :param script: Upgrade script's path
        :return: Whether the upgrade script should be run
        :rtype: bool
        """
        script_version = version.parse(script.parent.name)

        return not any(
            [
                not script.is_file(),
                re.match(r"^(\d+\.){2}\d+$", script.parent.name) is None,
                script_version <= version.parse(self.__latest_version()),
                script_version > version.parse(self.version),
            ]
        )

    def __list_upgrade_scripts(self) -> List[Path]:
        """List the upgrade scripts that should be run.

        :return: Upgrade scripts that should be run
        :rtype: List[Path]
        """
        return sorted(
            (s for s in self.upgrades_path.rglob("*.py") if self.__validate_upgrade_script(s)),
            key=lambda s: version.parse(s.parent.name),
        )

    def __run_upgrade_script(self, script: Path) -> None:
        """Run an upgrade script.

        :param script: Upgrade script's path
        """
        spec = spec_from_file_location(script.stem, script.as_posix())
        assert spec is not None and spec.loader is not None
        script_module: ModuleType = module_from_spec(spec)
        spec.loader.exec_module(script_module)
        script_module.run(self.config)
