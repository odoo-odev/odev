"""Self update Odev by pulling latest changes from the git repository."""

import contextlib
import inspect
import os
import pkgutil
import re
import sys
from argparse import Namespace
from collections import defaultdict
from collections.abc import Generator, Iterable, Iterator, Mapping, MutableMapping
from datetime import datetime
from functools import lru_cache
from importlib.abc import Loader
from importlib.machinery import FileFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import monotonic, sleep
from types import ModuleType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    NamedTuple,
    TypedDict,
    cast,
)

import networkx as nx
from git import GitCommandError, NoSuchPathError, Repo
from packaging import version

from odev._version import __version__
from odev.commands.database.delete import DeleteCommand
from odev.common import progress, string
from odev.common.commands import CommandType
from odev.common.commands.database import DatabaseType
from odev.common.config import Config
from odev.common.connectors.git import GitConnector, Stash
from odev.common.console import Console, console
from odev.common.errors import OdevError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.python import PythonEnv
from odev.common.store import DataStore
from odev.common.string import join_bullet
from odev.common.telemetry import Telemetry


try:
    from datetime import UTC
except ImportError:  # UTC is only available in Python 3.11+
    from datetime import timezone

    UTC = timezone.utc


__all__ = ["Odev"]


PRUNING_INTERVAL = 14
"""Number of days between each database pruning and time limit after which a database
must be dropped if not used.
"""

HOME_PATH = Path("~").expanduser() / "odev"
"""Local path to the odev home directory containing application data for the current user."""

VENVS_DIRNAME = "virtualenvs"
"""Name of the directory where virtual environments are stored."""

MIN_ARGV_LENGTH = 2
"""Minimum number of command line arguments required (command and subcommand)."""


class Manifest(TypedDict):
    """Plugin manifest information."""

    name: str
    description: str
    version: str
    depends: list[str]


class Plugin(NamedTuple):
    """Plugin information."""

    name: str
    path: Path
    manifest: Manifest


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

    commands: MutableMapping[str, type[CommandType]] = {}
    """Collection of existing and loaded commands."""

    executable: ClassVar[Path] = Path(sys.argv[0]).parent.resolve() / "odev.sh"
    """Path to the current executable."""

    _started: bool = False
    """Whether the framework has been started."""

    _command_stack: list[CommandType] = []
    """Stack of current commands being executed. Last command in list is the one currently running."""

    def __init__(self, test: bool = False):
        """Initialize the framework.

        :param test: Whether the framework is being initialized for testing purposes
        """
        self.start_time = monotonic()
        """Time when the framework was started."""

        self.in_test_mode = test
        """Whether the framework is in testing mode."""

        self._load_config()
        self.__class__.store = DataStore(self.name)
        self.telemetry = Telemetry(self)

    def __repr__(self) -> str:
        test_mode = ", test=True" if self.in_test_mode else ""
        return f"Odev(version={self.version}{test_mode})"

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
        return HOME_PATH

    @property
    def worktrees_path(self) -> Path:
        """Local path to the odev worktrees directory."""
        return self.home_path / "worktrees"

    @property
    def venvs_path(self) -> Path:
        """Local path to the odev virtual environments directory."""
        return self.home_path / VENVS_DIRNAME

    @property
    def base_path(self) -> Path:
        """Local path to the odev module."""
        return self.path / "odev"

    @property
    def tests_path(self) -> Path:
        """Local path to the tests directory."""
        return self.path / "tests"

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
        return self.base_path / "upgrades"

    @property
    def setup_path(self) -> Path:
        """Local path to the setup directory."""
        return self.base_path / "setup"

    @property
    def scripts_path(self) -> Path:
        """Local path to the directory where odoo-bin shell scripts are stored."""
        return self.base_path / "scripts"

    @property
    def static_path(self) -> Path:
        """Local path to the static directory where common immutable files are stored."""
        return self.base_path / "static"

    @property
    def dumps_path(self) -> Path:
        """Local path to the directory where database dumps are stored."""
        return self.config.paths.dumps

    @property
    def plugins(self) -> Generator[Plugin, None, None]:
        """Yields enabled plugins sorted topologically."""
        for plugin_name in self._plugins_dependency_tree():
            plugin_path = self.plugins_path / plugin_name.split("/")[-1].replace("-", "_")
            plugin_manifest = self._load_plugin_manifest(plugin_path)
            yield Plugin(plugin_name, plugin_path, plugin_manifest)

    @property
    def release(self) -> str:
        """Current release channel."""
        if not self.git.repository:
            return "<unknown>"

        if self.git.repository.head.is_detached:
            return "<detached>"

        branch = self.git.repository.active_branch.name

        if branch in ["main", "beta"]:
            return branch

        return f"dev:{branch}"

    def start(self, start_time: float | None = None) -> None:
        """Start the framework, check for updates and load plugins and commands.

        :param start_time: Time when the framework was started
        """
        if self._started:
            logger.debug("Framework already started")
            return

        logger.debug(
            f"Starting {self.name} version {string.stylize(self.version, 'repr.version')} "
            f"{'in test mode' if self.in_test_mode else ''}".strip()
        )

        if start_time:
            self.start_time = start_time

        self.plugins_path.mkdir(parents=True, exist_ok=True)
        self.check_release()
        self.update()

        with progress.spinner("Loading commands"):
            self.register_commands()
            self.register_plugin_commands()

        self.prune_databases()
        self._started = True

    def update(self, restart: bool = True, upgrade: bool = False) -> bool:
        """Update the framework and plugins if necessary.
        :param restart: Whether to restart the framework after updating.
        :param upgrade: Whether to force the upgrade process.
        """
        upgrade |= self.check_upgrade()

        logger.debug(f"Checking for updates in {self.name!r}")
        upgrade |= self._update(self.path)

        logger.debug("Checking for updates in plugins")
        plugins_upgrade = any(self._update(path, plugin) for plugin, path, _ in self.plugins)

        if upgrade or plugins_upgrade:
            self.config.update.date = datetime.now(UTC)
            self._set_version_after_update()
            self.upgrade()

            if restart:
                self.restart()

        return upgrade

    def _update(self, path: Path, plugin: str | None = None) -> bool:
        """Check for updates in the odev repository and download them if necessary.

        :param path: Path to a repository to update
        :return: Whether updates were pulled and installed
        :rtype: bool
        """
        path = path.resolve()

        try:
            repository = Repo(path)
        except NoSuchPathError as error:
            if plugin:
                logger.warning(f"Plugin {plugin!r} not found, maybe a missing dependency")
                self.install_plugin(plugin)

            raise OdevError(f"Error while updating {self.name}") from error

        manifest: Manifest = self._load_plugin_manifest(path)
        git = GitConnector(cast(str, manifest["name"]), path)

        if git.repository is None:
            raise OdevError(f"Repository for {self.name!r} not found at {path.as_posix()}")

        if not self.__date_check_interval() or not self.__git_branch_behind(git.repository):
            git.fetch()
            return False

        prompt_name = f"plugin {plugin}" if plugin else self.name
        logger.debug(f"Checking for updates in {git.name!r}")

        if not self.__update_prompt(prompt_name):
            return False

        with progress.spinner(f"Updating {prompt_name}"):
            if git.repository.head.is_detached:
                raise OdevError(
                    f"Cannot update {prompt_name} as the repository is in a detached HEAD state\n"
                    "Consider checking out the main branch for regular updates"
                )

            current_branch = git.repository.active_branch.name
            default_branch = git.default_branch

            if current_branch != default_branch:
                target = "Odev" if not plugin else f"Plugin {plugin!r}"
                logger.warning(
                    f"{target} is running from a non-standard branch {current_branch!r}, assuming your are in "
                    "development mode\nUpdates will not be pulled automatically\nConsider switching to branch "
                    f"{default_branch!r} for regular updates"
                )
                return True

            logger.debug(f"Pulling latest changes from {git.name!r} on branch {current_branch!r}")
            install_requirements = self.__requirements_changed(git.repository)
            head_commit = git.repository.commit().hexsha

            with Stash(git.repository):
                try:
                    repository.git.pull(repository.remote().name, current_branch)
                except GitCommandError as error:
                    error_message = f"Error while pulling latest changes for {prompt_name}: {error}"

                    if "fatal: Cannot rebase onto multiple branches" in str(error):
                        # Likely happening because of a race condition when a detached subprocess is fetching changes
                        # in the same repository, we can safely retry after a short wait
                        logger.debug(error_message)
                        sleep(0.5)
                        return self._update(path, plugin)

                    raise OdevError(error_message) from error

            if install_requirements:
                logger.debug(f"Installing new package requirements for {prompt_name!r}")
                PythonEnv().install_requirements(path)

            self._load_plugin_manifest.cache_clear()
            manifest = self._load_plugin_manifest(path)
            self.config.plugins.enabled = {*self.config.plugins.enabled, *manifest["depends"]}
            notes = self.__release_notes(git.repository, head_commit)

            if notes:
                sections = "\n".join(notes.values())
                logger.info(f"Updated {prompt_name}:\n\n{sections}")
                self.console.print(highlight=False)
                logger.info(f"Check the full changelog at {git.remote.url}/compare/{head_commit}...{current_branch}")

        return True

    def restart(self) -> None:
        """Restart the current process with the latest version of odev."""
        logger.debug("Restarting odev")
        os.execv(self.executable.as_posix(), [*sys.argv, f"--log-level={LOG_LEVEL}"])  # noqa: S606

    def _set_version_after_update(self):
        """Set the version of odev after an update by reading it from the _version.py file.

        :return: The version of odev after an update
        :rtype: version.Version
        """
        version_module_path = self.path / "odev" / "_version.py"
        spec = spec_from_file_location("_version", version_module_path)

        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load version module from {version_module_path}")

        version_module = module_from_spec(spec)
        spec.loader.exec_module(version_module)
        self.__class__.version = version_module.__version__

    def check_upgrade(self) -> bool:
        """Check whether the current version of odev is the latest available version.

        :return: Whether the current version is the latest available version
        :rtype: bool
        """
        new_version = version.parse(self.version)
        old_version = version.parse(self.config.update.version)
        versions = " to ".join([string.stylize(str(ver), "repr.version") for ver in (old_version, new_version)])
        logger.debug(f"Checking for existing upgrades from {versions}")
        return new_version > old_version

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
            current_version = script.parent.name

        self.config.update.version = self.version

    def prune_databases(self) -> None:
        """Prune existing local databases to free up resources and stay compliant with
        the General Data Protection Regulation (GDPR) as restored dumps may contain customer data.
        """
        last_pruning = (datetime.today() - self.config.pruning.date).days
        logger.debug(f"Last pruning of databases was {last_pruning} days ago")

        if last_pruning >= PRUNING_INTERVAL:
            from odev.common.databases.local import LocalDatabase  # noqa: PLC0415

            delete_command_cls = cast(type[CommandType], self.commands.get("delete"))
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
                        ("skip", "Do nothing and keep all databases for now"),
                        ("review", "Review databases and whitelist some of them"),
                        ("delete", "Delete all databases"),
                    ],
                    default="Skip",
                )

                if action == "skip":
                    logger.debug("Skipping database pruning")
                    return

                if action == "review":
                    whitelisted = self.console.checkbox(
                        "Select databases to whitelist\n    SPACE to whitelist\n    ENTER to validate",
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

    def import_commands(self, sources: Iterable[Path]) -> list[type[CommandType]]:
        """Import all commands from the source directories.

        :param sources: Source directories to search for commands.
        :return: List of imported command classes
        :rtype: List[CommandType]
        """
        command_modules = self.list_commands(sources)
        command_classes: list[type[CommandType]] = []

        for module_info in command_modules:
            if not isinstance(module_info.module_finder, FileFinder):
                raise TypeError("Module finder is not a FileFinder instance")

            module_path = Path(module_info.module_finder.path) / f"{module_info.name}.py"
            spec = spec_from_file_location(module_path.stem, module_path.as_posix())

            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module {module_info.name} from {module_path.as_posix()}")

            command_module: ModuleType = module_from_spec(spec)
            spec.loader.exec_module(command_module)
            command_classes.extend(command[1] for command in inspect.getmembers(command_module, self.__filter_commands))

        return command_classes

    def register_commands(self) -> None:
        """Register all commands from the commands directory."""
        for command_class in self.import_commands(self.commands_path.iterdir()) + self.import_commands(
            [self.commands_path]
        ):
            logger.debug(f"Registering command {command_class._name!r}")
            command_names = [command_class._name] + (list(command_class._aliases) or [])

            if any(name in command_names for name in self.commands):
                raise ValueError(f"Another command {command_class._name!r} is already registered")

            command_class.prepare_command(self)
            self.commands.update(dict.fromkeys(command_names, command_class))

    def register_plugin_commands(self) -> None:
        """Register commands for the plugins directories, pulling changes in plugins if an error arises while loading
        the commands.
        """
        try:
            self._register_plugin_commands()
        except Exception as error:
            logger.error(f"Error while loading plugins commands: {error}")

            with progress.spinner("Updating plugins"):
                for plugin, _, _ in self.plugins:
                    git = GitConnector(plugin)

                    if git.repository is None:
                        raise OdevError(f"Repository for plugin {plugin!r} not found") from error

                    with Stash(git.repository):
                        git.repository.remotes.origin.fetch()
                        git.repository.remotes.origin.pull(git.branch, rebase=True)

            self._register_plugin_commands()

    def _register_plugin_commands(self) -> None:
        """Register all commands from the plugins directories."""
        for plugin in self.plugins:
            logger.debug(
                f"Loading plugin {plugin.name!r} version {string.stylize(plugin.manifest['version'], 'repr.version')}"
            )

            for command_class in self.import_commands(plugin.path.glob("commands/**")):
                command_names = [command_class._name] + (list(command_class._aliases) or [])
                base_command_class = self.commands.get(command_class._name)

                if base_command_class is None or issubclass(base_command_class, command_class):
                    action = "Registering new command"
                else:
                    action = "Patching existing command"

                logger.debug(f"{action} {command_class._name!r} from plugin {plugin.name!r}")

                if (
                    command_class._name in self.commands
                    and base_command_class is not None
                    and command_class.__bases__ != base_command_class.__bases__
                ):

                    class PatchedCommand(command_class, base_command_class, *base_command_class.__bases__):
                        pass

                    command_class = PatchedCommand  # noqa: PLW2901 - we want to override the variable
                    PatchedCommand.__name__ = base_command_class.__name__

                command_class.prepare_command(self)
                self.commands.update(dict.fromkeys(command_names, command_class))

    def _load_config(self) -> None:
        """Reload the configuration file."""
        self.__class__.config = Config(self.name)

    def _plugin_is_installed(self, name: str) -> bool:
        """Check whether a plugin is installed.

        :param name: Name of the plugin to check
        :return: Whether the plugin is installed
        """
        plugin = next((p for p in self.plugins if name == p.name), None)

        if plugin is None:
            return False

        return plugin.path.is_symlink() or plugin.path.is_dir()

    def install_plugin(self, plugin: str, as_dependency: bool = False) -> None:
        """Install a new plugin from a git repository.

        :param plugin: Git repository of the plugin to install
        :param as_dependency: Whether the plugin is being installed as a dependency of another plugin
        """
        with progress.spinner(f"Installing plugin{' dependency' if as_dependency else ''} {plugin!r}"):
            repository = GitConnector(plugin)

            if repository.exists:
                repository.update()
            else:
                repository.clone()

            manifest = self._load_plugin_manifest(repository.path)

            if depends := manifest.get("depends"):
                for dependency in depends:
                    self.install_plugin(dependency, as_dependency=True)

            plugin_path = self.plugins_path / repository._repository.replace("-", "_")
            self.plugins_path.mkdir(parents=True, exist_ok=True)

            if self._plugin_is_installed(plugin):
                logger.info(f"Plugin {plugin!r} is already installed")
            else:
                try:
                    if not plugin_path.exists() and not plugin_path.is_symlink():
                        logger.debug(f"Creating symbolic link {plugin_path.as_posix()} to {repository.path.as_posix()}")
                        plugin_path.symlink_to(repository.path, target_is_directory=True)

                    self._load_config()
                    self._install_plugin_requirements(plugin_path)
                    self._setup_plugin(plugin_path, plugin)
                except Exception as error:
                    plugin_path.unlink(missing_ok=True)
                    raise OdevError(f"Error while installing requirements for plugin {plugin!r}: {error}") from error

                logger.info(f"Installed plugin{' dependency' if as_dependency else ''} {plugin!r}")

            self.config.plugins.enabled = {*self.config.plugins.enabled, plugin}
            self._plugins_dependency_tree.cache_clear()

    def uninstall_plugin(self, plugin: str) -> None:
        """Uninstall a plugin the plugins that depend on it.

        :param plugin: Name of the plugin to uninstall
        """
        if not self._plugin_is_installed(plugin):
            if plugin in self.config.plugins.enabled:
                self.config.plugins.enabled = {p for p in self.config.plugins.enabled if p != plugin}

            logger.info(f"Plugin {plugin!r} is not installed")
            return

        with progress.spinner(f"Uninstalling plugin {plugin!r}"):
            dependents: set[str] = set()

            for installed_plugin in self._plugins_dependency_tree():
                if installed_plugin == plugin:
                    continue

                installed_plugin_path = self.plugins_path / installed_plugin.split("/")[-1].replace("-", "_")
                manifest = self._load_plugin_manifest(installed_plugin_path)

                if any(dep in manifest.get("depends", []) for dep in dependents | {plugin}):
                    dependents.add(installed_plugin)

            if dependents:
                logger.warning(
                    f"Uninstalling plugin {plugin!r} will also uninstall the following dependent plugins:\n"
                    f"{string.join_bullet(list(dependents))}"
                )
            else:
                logger.warning(f"You are about to uninstall the plugin {plugin!r}")

            if not self.console.confirm("Do you want to continue?", default=False):
                raise OdevError("Aborting plugin uninstallation")

            for dependent in dependents | {plugin}:
                plugin_path = self.plugins_path / dependent.split("/")[-1].replace("-", "_")
                plugin_path.unlink(missing_ok=True)
                self.config.plugins.enabled = {p for p in self.config.plugins.enabled if p != dependent}
                logger.info(f"Uninstalled plugin {dependent!r}")

            self._load_config()
            self._plugins_dependency_tree.cache_clear()

    def _install_plugin_requirements(self, plugin_path: Path) -> None:
        """Install the requirements of a plugin.

        :param plugin_path: Path to the plugin to install requirements for
        """
        python = PythonEnv()

        if any(python.missing_requirements(plugin_path, raise_if_error=False)):
            python.install_requirements(plugin_path)

    def _setup_plugin(self, plugin_path: Path, plugin: str | None = None) -> None:
        """Run the setup script of a plugin if it exists.

        :param plugin_path: Path to the plugin to setup
        """
        setup_script = plugin_path / "setup.py"

        if setup_script.exists() and setup_script.is_file():
            logger.info("Running setup for plugin" + (f" {plugin!r}" if plugin else ""))
            spec = spec_from_file_location(f"{plugin_path.name}.setup", setup_script)

            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load setup module from {setup_script.as_posix()}")

            setup_module: ModuleType = module_from_spec(spec)
            cast(Loader, spec.loader).exec_module(setup_module)

            if hasattr(setup_module, "setup"):
                setup_module.setup(self)

    @lru_cache  # noqa: B019 - cache result as it won't change during execution
    def _load_plugin_manifest(self, plugin_path: Path) -> Manifest:
        """Load the manifest file of a plugin."""
        resolved_path = plugin_path.resolve()
        defaults: Manifest = {
            "name": f"{resolved_path.parent.name}/{resolved_path.name}",
            "version": "1.0.0",
            "description": "",
            "depends": [],
        }

        if not (plugin_path / "__manifest__.py").exists():
            return defaults

        spec = spec_from_file_location(f"{plugin_path.name}.__manifest__", (plugin_path / "__manifest__.py").as_posix())

        if spec is None:
            raise ImportError(f"Cannot load manifest module from {(plugin_path / '__manifest__.py').as_posix()}")

        manifest = module_from_spec(spec)
        cast(Loader, spec.loader).exec_module(manifest)

        return {
            **defaults,
            "version": getattr(manifest, "__version__", defaults["version"]),
            "description": getattr(manifest, "__doc__", defaults["description"]),
            "depends": getattr(manifest, "depends", defaults["depends"]),
        }

    @lru_cache  # noqa: B019 - cache result as it won't change during execution
    def _plugins_dependency_tree(self) -> list[str]:
        """Order plugins by mutual dependencies, the first one in the returned list being the first one that needs to
        be imported to respect the dependency graph.
        """
        graph = nx.DiGraph()

        for plugin_path in self.plugins_path.iterdir():
            manifest = self._load_plugin_manifest(plugin_path)
            graph.add_node(manifest["name"])

            for dependency in manifest["depends"]:
                graph.add_edge(dependency, manifest["name"])

        try:
            resolved_graph: list[str] = list(nx.topological_sort(graph))
            logger.debug(f"Resolved plugins dependency tree:\n{join_bullet(resolved_graph)}")
        except nx.NetworkXUnfeasible as exception:
            raise OdevError("Circular dependency detected in plugins") from exception

        return resolved_graph

    def parse_arguments(self, command_cls: type[CommandType], *args) -> Namespace:
        """Parse arguments for a command.

        :param command_cls: Command class to parse arguments for
        :param args: Arguments to parse
        :return: Parsed arguments
        """
        try:
            logger.debug(f"Parsing command arguments '{' '.join(args)}'")
            arguments = command_cls.parse_arguments(args)
            command_cls.check_arguments(arguments)
        except SystemExit as exception:
            raise command_cls.error(None, str(exception)) from exception
        return arguments

    def run_command(
        self,
        name: str,
        *cli_args: str,
        history: bool = False,
        database: DatabaseType | None = None,
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
                    command = command_cls(arguments, database=database)  # type: ignore [call-arg]
                else:
                    command = command_cls(arguments)

            command._argv = cli_args
            logger.debug(f"Running {command!r}")
            self._command_stack.append(command)
            telemetry = self.telemetry.send(command)
            command.run()
            self._command_stack.pop()
        except OdevError as exception:
            command_errored = True
            logger.error(str(exception))
        else:
            if history:
                self.store.history.set(command)
        finally:
            try:
                logger.debug(f"Cleaning up after {command!r}")
                command.cleanup()

                if telemetry and self.config.telemetry.enabled:
                    telemetry[0].join()
                    telemetry_line = telemetry[1].get()

                    if telemetry_line is not None:
                        self.telemetry.update(telemetry_line)

            except UnboundLocalError:
                pass

        return not command_errored

    def dispatch(self, argv: list[str] | None = None) -> None:
        """Handle commands and arguments as received from the terminal.
        :param argv: Optional list of command-line arguments used to override arguments received from the CLI.
        """
        argv = (argv or sys.argv)[1:]

        if (
            not len(argv)
            or (
                len(argv) >= MIN_ARGV_LENGTH
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

    def check_release(self) -> None:
        """Check if a new release is available."""
        if not self.git.repository:
            return

        if self.git.repository.active_branch.name != self.config.update.release:
            logger.warning(
                f"Release channel is set to {self.config.update.release!r} in configuration file "
                f"but repository is on branch {self.git.repository.active_branch.name!r}\n"
                "Consider running 'odev config update.release <branch>' to switch odev and its plugins to the desired "
                "release channel"
            )

    def switch_release_channel(self, branch: str) -> None:
        """Switch the release channel to the given branch."""
        with progress.spinner(f"Switching odev to {branch!r} release channel"):
            self.__checkout_release_channel(self.git, branch)

        with progress.spinner(f"Switching plugins to {branch!r} release channel"):
            for plugin in self.plugins:
                self.__checkout_release_channel(GitConnector(plugin.name), branch)

        self.config.update.release = branch
        logger.info(f"Switched release channel to {branch!r}")

    # --- Private methods ------------------------------------------------------

    def __checkout_release_channel(self, repo: GitConnector, branch: str) -> None:
        """Checkout the release channel."""
        if not repo.repository:
            logger.warning(f"Directory {repo.name!r} is not a git repository, skipping")
            return

        if repo.repository.head.is_detached:
            logger.warning(f"Repository {repo.name!r} is detached, please switch manually")
            return

        current_branch = repo.repository.active_branch.name

        if current_branch not in ["main", "beta"]:
            logger.warning(f"Repository {repo.name!r} is not on 'main' or 'beta' branch, please switch manually")
            return

        if current_branch == branch:
            logger.info(f"Repository {repo.name!r} is already on {branch!r} branch, skipping")
            return

        with contextlib.suppress(GitCommandError):
            repo.checkout(branch)
            self._install_plugin_requirements(repo.path)

    def __filter_commands(self, attribute: Any) -> bool:
        """Filter module attributes to extract commands.

        :param attribute: Module attribute
        :return: Whether the module attribute is a command
        :rtype: bool
        """
        from odev.common.commands.base import Command  # noqa: PLC0415 - avoid circular import

        return (
            inspect.isclass(attribute)
            and issubclass(attribute, Command)
            and not attribute.is_abstract()
            and "." not in attribute.__module__
        )

    def __git_branch_behind(self, repository: Repo) -> bool:
        """Assess whether the current branch is behind the remote tracking branch.

        :param repository: Git repository to check for pending incoming changes
        :return: Whether the branch is behind the remote tracking branch
        :rtype: bool
        """
        remote_branch = repository.active_branch.tracking_branch()

        if remote_branch is None:
            return False

        repository_path = Path(repository.working_dir)
        repository_name = f"'{repository_path.parent.name}/{repository_path.name}'"
        rev_list: str = repository.git.rev_list("--left-right", "--count", f"{remote_branch.name}...HEAD")
        commits_behind, commits_ahead = (int(commits_count) for commits_count in rev_list.split("\t"))
        message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
        message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"

        if commits_behind and commits_ahead:
            logger.debug(f"Repository {repository_name} is {message_behind} and {message_ahead} {remote_branch.name!r}")
        elif commits_behind:
            logger.debug(f"Repository {repository_name} is {message_behind} {remote_branch.name!r}")
        elif commits_ahead:
            logger.debug(f"Repository {repository_name} is {message_ahead} {remote_branch.name!r}")
        else:
            logger.debug(f"Repository {repository_name} is up-to-date with {remote_branch.name!r}")

        if commits_ahead:
            logger.debug("Running in development mode (no self-update)")
            return False

        return bool(commits_behind)

    def __release_notes(self, repository: Repo, from_commit: str) -> Mapping[str, str]:
        """Retrieve the release notes of the latest version of the repository.

        :param repository: Git repository to retrieve release notes from
        :param from_commit: Commit hash to start retrieving release notes from
        :return: Release notes grouped by type
        :rtype: Mapping[str, str]
        """
        logs = repository.git.log("--oneline", "--no-decorate", f"{from_commit}..").strip().splitlines()
        re_note = re.compile(r"^(?P<hash>[0-9a-f]+)\s\[(?P<tag>[A-Z]{3,})\]\s?(?:(?P<files>[^:]*?):)?\s?(?P<note>.+)$")
        grouped = defaultdict(list)

        for line in logs:
            match = re_note.match(line)

            if not match or not match.groups():
                continue

            groups = match.groupdict()
            grouped[groups["tag"].lower()].append(groups["note"])

        subtitles = {
            "add": string.stylize(":sparkles: New Features", "bold"),
            "imp": string.stylize(":arrow_double_up: Improvements", "bold"),
            "fix": string.stylize(":bug: Bug Fixes", "bold"),
        }

        return {
            key: f"{subtitles[key]}\n{join_bullet([note[0].upper() + note[1:] for note in grouped[key]])}\n"
            for key in subtitles
            if key in grouped
        }

    def __requirements_changed(self, repository: Repo) -> bool:
        """Assess whether the requirements.txt file was modified.

        :param repository: Git repository to check for changes in requirements.txt file
        :return: Whether the requirements.txt file has changed
        :rtype: bool
        """
        requirements_file = Path(repository.working_dir) / "requirements.txt"
        remote_branch = repository.active_branch.tracking_branch()
        tracking_ref = remote_branch.name if remote_branch is not None else "HEAD"
        diff = repository.git.diff("--name-only", tracking_ref, "--", requirements_file).strip()

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

    def __list_upgrade_scripts(self) -> list[Path]:
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

        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load upgrade script module from {script.as_posix()}")

        script_module: ModuleType = module_from_spec(spec)
        spec.loader.exec_module(script_module)

        try:
            script_module.run(self)
        except Exception as e:
            raise RuntimeError(f"Error while running upgrade script {script.parent.name}: {e.args[0]}") from e
        else:
            self.config.update.version = script.parent.name
