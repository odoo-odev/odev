"""Self update Odev by pulling latest changes from the git repository."""

import inspect
import os
import pkgutil
import re
import sys
from datetime import datetime, timezone
from importlib.machinery import FileFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    ClassVar,
    Generic,
    Iterable,
    Iterator,
    List,
    Literal,
    MutableMapping,
    Optional,
    Type,
    cast,
)

from git import Repo
from packaging import version

from odev._version import __version__
from odev.commands.database.delete import DeleteCommand
from odev.common import progress
from odev.common.commands import CommandType
from odev.common.commands.database import DatabaseCommand, DatabaseType
from odev.common.config import Config
from odev.common.connectors.git import GitConnector, Stash
from odev.common.console import Console, console
from odev.common.errors import OdevError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.python import PythonEnv
from odev.common.store import DataStore
from odev.common.string import join_bullet


__all__ = ["Odev"]


PRUNING_INTERVAL = 14
"""Number of days between each database pruning and time limit after which a database
must be dropped if not used.
"""


logger = logging.getLogger(__name__)


class Odev(Generic[CommandType]):
    """Main framework class."""

    version: ClassVar[str] = __version__
    """Odev version."""

    path: ClassVar[Path] = Path(__file__).parents[2]
    """Local path to the odev repository."""

    config: ClassVar[Config]
    """Odev configuration."""

    store: ClassVar[DataStore]
    """Odev data storage."""

    commands: MutableMapping[str, Type[CommandType]] = {}
    """Collection of existing and loaded commands."""

    executable: ClassVar[Path] = Path(sys.argv[0])
    """Path to the current executable."""

    _started: bool = False
    """Whether the framework has been started."""

    def __init__(self, test: bool = False):
        """Initialize the framework.
        :param test: Whether the framework is being initialized for testing purposes
        """
        self.in_test_mode = test
        """Whether the framework is in testing mode."""

        self.__class__.config = Config(self.name)
        self.__class__.store = DataStore(self.name)

    def __repr__(self) -> str:
        return f"Odev(version={self.version})"

    @property
    def git(self) -> GitConnector:
        """Git repository of the local odev folder."""
        return GitConnector(f"{self.path.parent.name}/{self.path.name}", self.path)

    @property
    def name(self) -> Literal["odev", "odev-test"]:
        """Name of the framework."""
        return "odev" if not self.in_test_mode else "odev-test"

    @property
    def console(self) -> Console:
        """Rich console instance to display information to users."""
        return console

    @property
    def home_path(self) -> Path:
        """Local path to the odev home directory containing application data
        for the current user.
        """
        return Path("~").expanduser() / "odev"

    @property
    def base_path(self) -> Path:
        """Local path to the odev module."""
        return self.path / "odev"

    @property
    def tests_path(self) -> Path:
        """Local path to the tests directory."""
        return self.path / "tests/resources"

    @property
    def plugins_path(self) -> Path:
        """Local path to the plugins directory."""
        return self.base_path / "plugins"

    @property
    def commands_path(self) -> Path:
        """Local path to the commands directory."""
        return self.base_path / "commands"

    @property
    def upgrades_path(self) -> Path:
        """Local path to the upgrades directory."""
        return (self.tests_path if self.in_test_mode else self.base_path) / "upgrades"

    @property
    def setup_path(self) -> Path:
        """Local path to the setup directory."""
        return (self.tests_path if self.in_test_mode else self.base_path) / "setup"

    @property
    def scripts_path(self) -> Path:
        """Local path to the directory where odoo-bin shell scripts are stored."""
        return (self.tests_path if self.in_test_mode else self.base_path) / "scripts"

    @property
    def static_path(self) -> Path:
        """Local path to the static directory where common immutable files are stored."""
        return self.base_path / "static"

    @property
    def dumps_path(self) -> Path:
        """Local path to the directory where database dumps are stored."""
        return self.config.paths.dumps

    @property
    def plugins(self) -> List[str]:
        """List of enabled plugins."""
        return [plugin for plugin in self.config.plugins.enabled if plugin]

    def start(self) -> None:
        """Start the framework, check for updates and load plugins and commands."""
        if self._started:
            return logger.debug("Framework already started")

        logger.debug(
            f"Starting {self.name} version [repr.version]{self.version}[/repr.version] "
            f"{'in test mode' if self.in_test_mode else ''}".strip()
        )

        self.plugins_path.mkdir(parents=True, exist_ok=True)
        self.update()

        with progress.spinner("Loading commands"):
            self.register_commands()
            self.register_plugin_commands()

        self.prune_databases()
        self._started = True

    def update(self, restart: bool = True, upgrade: bool = False) -> None:
        """Update the framework and plugins if necessary.
        :param restart: Whether to restart the framework after updating.
        :param upgrade: Whether to force the upgrade process.
        """
        if (
            upgrade
            or self._update(self.path, self.name)
            or any(
                self._update(path, f"plugin {name}")
                for path, name in [
                    (self.plugins_path / plugin.split("/")[-1].replace("-", "_"), plugin) for plugin in self.plugins
                ]
            )
        ):
            self.config.update.date = datetime.now(timezone.utc)
            self.upgrade()

            if restart:
                self.restart()

    def load_plugins(self) -> None:
        """Load plugins from the configuration file and register them in the plugin directory."""
        self.plugins_path.mkdir(parents=True, exist_ok=True)

        for plugin in self.plugins:
            logger.debug(f"Loading plugin {plugin!r}")
            repository = GitConnector(plugin)

            if not repository.exists:
                repository.clone()

            repository.update()
            plugin_path = self.plugins_path.joinpath(repository._repository.replace("-", "_"))

            if not plugin_path.exists():
                logger.debug(f"Creating symbolic link {plugin_path.as_posix()} to {repository.path.as_posix()}")
                plugin_path.symlink_to(repository.path, target_is_directory=True)

            python = PythonEnv()

            if list(python.missing_requirements(plugin_path, False)):
                python.install_requirements(plugin_path)

    def _update(self, path: Path, prompt_name: str) -> bool:
        """Check for updates in the odev repository and download them if necessary.
        :param path: Path to a repository to update
        :return: Whether updates were pulled and installed
        :rtype: bool
        """
        path = path.resolve()
        repository = Repo(path.as_posix())
        repository_name = "/".join(repository.remotes.origin.url.split("/")[-2:]).split(":")[-1].removesuffix(".git")
        git = GitConnector(repository_name, path)
        assert git.repository is not None

        if not self.__date_check_interval() or not self.__git_branch_behind(git.repository):
            git.fetch()
            return False

        logger.debug(f"Checking for updates in {git.name!r}")

        if not self.__update_prompt(prompt_name):
            return False

        with progress.spinner(f"Updating {prompt_name!r}"):
            logger.debug(
                f"Pulling latest changes from {git.name!r} "
                f"on branch '{git.repository.active_branch.tracking_branch()}'"
            )
            install_requirements = self.__requirements_changed(git.repository)

            with Stash(git.repository):
                repository.remotes.origin.pull()

            if install_requirements:
                logger.debug(f"Installing new package requirements for {prompt_name!r}")
                PythonEnv().install_requirements(path)

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
        logger.debug("Checking for existing upgrades")
        return version.parse(self.version) > version.parse(self.config.update.version)

    def upgrade(self) -> None:
        """Upgrade the current version of odev."""
        if not self.check_upgrade():
            return

        current_version = self.config.update.version

        logger.debug(f"Upgrading odev from version {current_version} to {self.version}")
        scripts = self.__list_upgrade_scripts()

        for script in scripts:
            logger.debug(f"Running upgrade script [{current_version} -> {script.parent.name}]")
            self.__run_upgrade_script(script)

        self.config.update.version = self.version

    def prune_databases(self) -> None:
        """Prune existing local databases to free up resources and stay compliant with
        the General Data Protection Regulation (GDPR) as restored dumps may contain customer data.
        """
        last_pruning = (datetime.today() - self.config.pruning.date).days
        logger.debug(f"Last pruning of databases was {last_pruning} days ago")

        if last_pruning >= PRUNING_INTERVAL:
            from odev.common.databases.local import LocalDatabase

            delete_command_cls = cast(Type[CommandType], self.commands.get("delete"))
            delete_command = cast(DeleteCommand, delete_command_cls(delete_command_cls.parse_arguments([])))

            def filter_databases(name: str) -> bool:
                database = LocalDatabase(name)
                today = datetime.today()
                return not database.whitelisted and (today - (database.last_date or today)).days >= PRUNING_INTERVAL

            databases = delete_command.list_databases(predicate=filter_databases)

            if databases:
                logger.warning(
                    f"Some databases have not been used for {PRUNING_INTERVAL} days and will be pruned:"
                    f"\n{join_bullet(databases)}"
                )
                action = self.console.select(
                    "What do you want to do?",
                    choices=[
                        ("delete", "Delete all databases"),
                        ("review", "Review databases and whitelist some of them"),
                        ("skip", "Do nothing and keep all databases for now"),
                    ],
                    default="Skip",
                )

                if action == "skip":
                    return logger.debug("Skipping database pruning")

                if action == "review":
                    whitelisted = self.console.checkbox(
                        "Select databases to whitelist",
                        choices=[(database, database) for database in databases],
                    )

                    for database in whitelisted:
                        LocalDatabase(database).whitelisted = True
                        databases.remove(database)

            if databases:
                for database in databases:
                    delete_command.delete_one(LocalDatabase(database))

                logger.info(f"Deleted {len(databases)} databases:\n{join_bullet(databases)}")

            self.config.pruning.date = datetime.today()

    def list_commands(self, sources: Iterable[Path]) -> Iterator[pkgutil.ModuleInfo]:
        """Find command modules in the source directories.
        :param sources: Source directories to search for commands.
        :return: Iterator over command modules.
        """
        command_dirs = [path for path in sources if path.is_dir() and not path.name.startswith("_")]
        return pkgutil.iter_modules([d.as_posix() for d in command_dirs])

    def import_commands(self, sources: Iterable[Path]) -> List[Type[CommandType]]:
        """Import all commands from the source directories.
        :param sources: Source directories to search for commands.
        :return: List of imported command classes
        :rtype: List[CommandType]
        """
        command_modules = self.list_commands(sources)
        command_classes: List[Type[CommandType]] = []

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
        for command_class in self.import_commands(self.commands_path.iterdir()):
            logger.debug(f"Registering command {command_class._name!r}")
            command_names = [command_class._name] + (list(command_class._aliases) or [])

            if any(name in command_names for name in self.commands.keys()):
                raise ValueError(f"Another command {command_class._name!r} is already registered")

            command_class.prepare_command(self)
            self.commands.update({name: command_class for name in command_names})

    def register_plugin_commands(self) -> None:
        """Register commands for the plugins directories, pulling changes in plugins if an error arises while loading
        the commands.
        """
        try:
            self._register_plugin_commands()
        except Exception as error:
            logger.debug(f"Error while loading plugins commands: {error}")

            with progress.spinner("Updating plugins"):
                for plugin in self.plugins:
                    git = GitConnector(plugin)
                    assert git.repository is not None

                    with Stash(git.repository):
                        git.repository.remotes.origin.fetch()
                        git.repository.remotes.origin.pull(git.branch, rebase=True)

            self._register_plugin_commands()

    def _register_plugin_commands(self) -> None:
        """Register all commands from the plugins directories."""
        for plugin_path in self.plugins_path.iterdir():
            logger.debug(f"Loading plugin {plugin_path.name!r}")

            for command_class in self.import_commands(plugin_path.glob("commands/**")):
                command_names = [command_class._name] + (list(command_class._aliases) or [])
                base_command_class = self.commands.get(command_class._name)

                if (
                    base_command_class is not None
                    and any(name in command_names for name in self.commands.keys())
                    and command_class.__bases__ == base_command_class.__bases__
                ):
                    continue  # Ignore base command import when used in python inheritance

                if base_command_class is None or issubclass(base_command_class, command_class):
                    action = "Registering new command"
                else:
                    action = "Patching existing command"

                logger.debug(f"{action} {command_class._name!r} from plugin {plugin_path.name!r}")

                if (
                    command_class._name in self.commands.keys()
                    and base_command_class is not None
                    and command_class.__bases__ != base_command_class.__bases__
                ):

                    class PatchedCommand(command_class, base_command_class, *base_command_class.__bases__):  # type: ignore [valid-type,misc]  # noqa: B950
                        pass

                    command_class = PatchedCommand
                    PatchedCommand.__name__ = base_command_class.__name__

                command_class.prepare_command(self)
                self.commands.update({name: command_class for name in command_names})  # type: ignore [assignment]

    def parse_arguments(self, command_cls: Type[CommandType], *args):
        """Parse arguments for a command.

        :param command_cls: Command class to parse arguments for
        :param args: Arguments to parse
        :return: Parsed arguments
        """
        try:
            logger.debug(f"Parsing command arguments '{' '.join(args)}'")
            arguments = command_cls.parse_arguments(args)
        except SystemExit as exception:
            raise command_cls.error(None, str(exception))  # type: ignore [call-arg]
        return arguments

    def run_command(
        self,
        name: str,
        *cli_args: str,
        history: bool = False,
        database: Optional[DatabaseType] = None,
    ) -> bool:
        """Run a command with the given arguments.

        :param name: Name of the command to run.
        :param cli_args: Arguments to pass to the command.
        :param history: Whether to add the command to the command history.
        :param database: Database to pass to the command.
        """
        command_cls = self.commands.get(name)

        if command_cls is None:
            logger.error(f"Command {name!r} not found")
            return False

        command: CommandType
        command_errored: bool = False

        try:
            if database is None:
                arguments = self.parse_arguments(command_cls, *cli_args)
                command = command_cls(arguments)
            else:
                cli_args = (database.name, *cli_args)
                arguments = self.parse_arguments(command_cls, *cli_args)

                if "database" in inspect.getfullargspec(command_cls.__init__).args:
                    command = cast(Type[DatabaseCommand], command_cls)(arguments, database=database)
                else:
                    command = command_cls(arguments)

            command._argv = cli_args

            logger.debug(f"Dispatching {command!r}")
            command.run()
        except OdevError as exception:
            command_errored = True
            logger.error(str(exception))
        else:
            if history:
                self.store.history.set(command)
        finally:
            try:
                command.cleanup()  # type: ignore [unbound-variable]
            except UnboundLocalError:
                pass

        return not command_errored

    def dispatch(self) -> None:
        """Handle commands and arguments as received from the terminal."""
        argv = sys.argv[1:]

        if (
            not len(argv)
            or (
                len(argv) >= 2
                and any(
                    arg in filter(lambda a: a.startswith("-"), cast(CommandType, self.commands.get("help"))._aliases)
                    for arg in argv
                )
            )
            or argv[0].startswith("-")
        ):
            logger.debug("Help argument or no command provided, falling back to help command")
            argv.insert(0, "help")

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

    def __git_branch_behind(self, repository: Repo) -> bool:
        """Assess whether the current branch is behind the remote tracking branch.
        :param repository: Git repository to check for pending incoming changes
        :return: Whether the branch is behind the remote tracking branch
        :rtype: bool
        """
        remote_branch = repository.active_branch.tracking_branch()

        if remote_branch is None:
            return False

        rev_list: str = repository.git.rev_list("--left-right", "--count", f"{remote_branch.name}...HEAD")
        commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split("\t")]
        message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
        message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"

        if commits_behind and commits_ahead:
            logger.debug(f"Repository is {message_behind} and {message_ahead} {remote_branch.name!r}")
        elif commits_behind:
            logger.debug(f"Repository is {message_behind} {remote_branch.name!r}")
        elif commits_ahead:
            logger.debug(f"Repository is {message_ahead} {remote_branch.name!r}")
        else:
            logger.debug(f"Repository is up-to-date with {remote_branch.name!r}")

        if commits_ahead:
            logger.debug("Running in development mode (no self-update)")
            return False

        return bool(commits_behind)

    def __requirements_changed(self, repository: Repo) -> bool:
        """Assess whether the requirements.txt file was modified.
        :param repository: Git repository to check for changes in requirements.txt file
        :return: Whether the requirements.txt file has changed
        :rtype: bool
        """
        requirements_file = Path(repository.working_dir) / "requirements.txt"
        remote_branch = repository.active_branch.tracking_branch()
        tracking_ref = remote_branch.name if remote_branch is not None else "HEAD"
        diff = repository.git.diff("--name-only", tracking_ref, requirements_file).strip()

        if diff == requirements_file.as_posix():
            logger.debug("Repository requirements have changed since last version")

        return bool(diff)

    def __date_check_interval(self) -> bool:
        """Check whether the last check date is older than today minus the check interval.
        :return: Whether the last check date is older than today minus the check interval
        :rtype: bool
        """
        return (datetime.today() - self.config.update.date).days >= self.config.update.interval

    def __update_prompt(self, name: str) -> bool:
        """Prompt the user to update odev if a new version is available.
        :param name: Name of the repository to update
        :return: Whether the user wants to update odev
        :rtype: bool
        """
        if self.config.update.mode == "ask":
            return self.console.confirm(f"An update is available for {name}, do you want to download it now?")

        return self.config.update.mode == "always"

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
                script_version <= version.parse(self.config.update.version),
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

        try:
            script_module.run(self)
        except Exception as e:
            raise RuntimeError(f"Error while running upgrade script {script.parent.name}: {e.args[0]}") from e
        else:
            self.config.update.version = script.parent.name
