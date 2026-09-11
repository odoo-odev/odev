"""Self update Odev by pulling latest changes from the git repository."""

import contextlib
import importlib
import inspect
import os
import pkgutil
import re
import sys
from argparse import Namespace
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from importlib.abc import Loader
from importlib.machinery import FileFinder, ModuleSpec
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import monotonic, sleep
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    cast,
)

from git import GitCommandError, NoSuchPathError, Repo
from packaging import version

from odev._version import __version__
from odev.common import progress, string
from odev.common.commands import CommandType
from odev.common.commands.database import DatabaseType
from odev.common.commands.registry import CommandRegistry
from odev.common.config import CONFIG_DIR, Config
from odev.common.connectors.git import GitConnector, Stash
from odev.common.console import Console, console
from odev.common.errors import OdevError
from odev.common.logging import LOG_LEVEL, logging
from odev.common.plugins import (
    PLUGIN_MANIFEST_FILENAME,
    Discovery,
    Manifest,
    Plugin,
    SkippedPlugin,
    forget_plugins,
    installed_plugins,
    parse_plugin_manifest,
    plugin_identity,
    plugin_link,
    plugin_module_name,
    plugins_requiring,
    read_plugin_manifest,
)
from odev.common.python import PythonEnv
from odev.common.store import DataStore
from odev.common.string import join_bullet
from odev.common.telemetry import Telemetry


if TYPE_CHECKING:
    from odev.common.odoobin import OdoobinProcess as OdoobinProcessType


try:
    from datetime import UTC
except ImportError:  # UTC is only available in Python 3.11+
    from datetime import timezone

    UTC = timezone.utc


# The plugin primitives now live in `odev.common.plugins`; they stay re-exported here as plugins import them
# from this module.
__all__ = [
    "PLUGIN_MANIFEST_FILENAME",
    "Manifest",
    "Odev",
    "Plugin",
    "parse_plugin_manifest",
    "plugin_module_name",
]


PRUNING_INTERVAL = 14
"""Number of days between each database pruning and time limit after which a database
must be dropped if not used.
"""

MAX_GIT_PULL_RETRIES = 3
"""Maximum number of retries for a git pull operation."""

HOME_PATH = Path("~").expanduser() / "odev"
"""Local path to the odev home directory containing application data for the current user."""

VENVS_DIRNAME = "virtualenvs"
"""Name of the directory where virtual environments are stored."""

MIN_ARGV_LENGTH = 2
"""Minimum number of command line arguments required (command and subcommand)."""

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

    commands: "CommandRegistry"
    """Collection of existing commands, imported on demand."""

    executable: ClassVar[Path] = Path(sys.argv[0]).parent.resolve() / "odev.sh"
    """Path to the current executable."""

    _started: bool = False
    """Whether the framework has been started."""

    _plugin_requirements_checked: bool = False
    """Whether missing python requirements of enabled plugins have already been checked during this run."""

    _command_stack: list[CommandType] = []
    """Stack of current commands being executed. Last command in list is the one currently running."""

    def __init__(self, test: bool = False, name: str | None = None):
        """Initialize the framework.

        :param test: Whether the framework is being initialized for testing purposes
        :param name: Namespace of the framework, overriding the one inferred from the test mode
        """
        self.start_time = monotonic()
        """Time when the framework was started."""

        self.in_test_mode = test
        """Whether the framework is in testing mode."""

        self._name = name
        """Namespace explicitly assigned to this instance, if any."""

        self.commands = CommandRegistry(self)
        """Collection of existing commands, imported on demand."""

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
    def name(self) -> str:
        """Name of the framework, and the namespace of everything it owns.

        The configuration file and the datastore database are both named after it, so an instance given an
        explicit name works on its own resources rather than on the ones of the user.
        """
        if self._name is not None:
            return self._name

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
        return CONFIG_DIR / "plugins"

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
    def plugins(self) -> list[Plugin]:
        """The plugins odev loads, in the order their dependencies require them to be imported.

        A plugin is a link under the plugins directory and nothing else, so this reads the filesystem and never
        consults the configuration nor the network.
        """
        return self._plugin_discovery().loaded

    @property
    def skipped_plugins(self) -> list[SkippedPlugin]:
        """The plugins that are installed but that could not be loaded, each with the reason it was left out."""
        return self._plugin_discovery().skipped

    def _plugin_discovery(self) -> Discovery:
        """Read the plugins directory.

        The result is cached against the modification time of the directory, so calling this repeatedly reads the
        filesystem once and picks up a link that changed on its own.

        :return: The plugins to load and the ones that were skipped
        """
        return installed_plugins(self.plugins_path)

    def _forget_plugins(self) -> None:
        """Discard the discovered plugins so the next access reads the plugins directory again."""
        forget_plugins()

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

    @property
    def odoobin_process_class(self) -> "type[OdoobinProcessType]":
        """The class used to spawn Odoo processes. Can be overridden by plugins."""
        from odev.common.odoobin import OdoobinProcess  # noqa: PLC0415

        return getattr(self, "_odoobin_process_class", OdoobinProcess)

    @odoobin_process_class.setter
    def odoobin_process_class(self, value: "type[OdoobinProcessType]") -> None:
        self._odoobin_process_class = value

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

        if self._should_update_now():
            self.check_release()
            self.update()

        with progress.spinner("Loading commands"):
            self.load_plugins()

            # Importing every command module only to read its name makes each run pay for every command, plugins
            # included. Do it once and remember the outcome until the commands on disk actually change.
            fingerprint = self._commands_fingerprint()

            if not self.commands.load(fingerprint):
                self.register_commands()
                self.register_plugin_commands()
                self.commands.save(fingerprint)

        self.prune_databases()
        self.telemetry.flush()
        self._started = True

    def update(self, restart: bool = True, upgrade: bool = False) -> bool:
        """Update the framework and plugins if necessary.
        :param restart: Whether to restart the framework after updating.
        :param upgrade: Whether to force the upgrade process.
        """
        logger.debug(f"Checking for updates in {self.name!r}")
        repo_updated = self._update(self.path)

        logger.debug("Checking for updates in plugins")
        plugins_upgrade = any(self._update(path, plugin) for plugin, path, _ in self.plugins)

        updated = repo_updated or plugins_upgrade or upgrade
        self.config.update.date = datetime.now()

        if updated:
            self._set_version_after_update()
            self.upgrade()

            if restart:
                self.restart()

        return updated

    def _update(self, path: Path, plugin: str | None = None, _retry: int = 0) -> bool:
        """Check for updates in the odev repository and download them if necessary.

        :param path: Path to a repository to update
        :param _retry: Internal retry counter for race condition handling.
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

        git = GitConnector(plugin_identity(path.resolve()), path)

        if git.repository is None:
            raise OdevError(f"Repository for {self.name!r} not found at {path.as_posix()}")

        prompt_name = f"plugin {plugin}" if plugin else self.name
        logger.debug(f"Checking for updates in {git.name!r}")

        if not self.__git_branch_behind(git.repository):
            git.fetch(detached=False)

            if not self.__git_branch_behind(git.repository):
                logger.debug(f"No update available for {git.name!r}")
                return False

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

            if current_branch not in (default_branch, "beta"):
                target = "Odev" if not plugin else f"Plugin {plugin!r}"
                logger.warning(
                    f"{target} is running from a non-standard branch {current_branch!r}, assuming your are in "
                    "development mode\nUpdates will not be pulled automatically\nConsider switching to branch "
                    f"{default_branch!r} or 'beta' for regular updates"
                )
                return False

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
                        if _retry >= MAX_GIT_PULL_RETRIES:
                            raise OdevError(error_message) from error

                        logger.debug(error_message)
                        sleep(0.5)
                        return self._update(path, plugin, _retry=_retry + 1)

                    raise OdevError(error_message) from error

            if install_requirements:
                logger.debug(f"Installing new package requirements for {prompt_name!r}")
                PythonEnv().install_requirements(path)

            self._forget_plugins()
            self._install_new_dependencies(path, plugin)
            self._show_release_notes(git, head_commit, prompt_name)

        return True

    def _install_new_dependencies(self, path: Path, plugin: str | None) -> None:
        """Install the dependencies a plugin gained since it was last updated.

        :param path: Path to the repository that was just pulled
        :param plugin: Name of the plugin, `None` when odev itself was updated
        """
        manifest = read_plugin_manifest(path, plugin) if plugin else None

        for dependency in manifest["depends"] if manifest else []:
            if not self._plugin_is_installed(dependency):
                self.install_plugin(dependency, as_dependency=True)

    def _show_release_notes(self, git: GitConnector, head_commit: str, prompt_name: str):
        if not git.repository or not git.remote:
            return

        if notes := self.__release_notes(git.repository, head_commit):
            sections = "\n".join(notes.values())
            logger.info(f"Updated {prompt_name}:\n\n{sections}")
            self.console.print(highlight=False)
            github_url = git.remote.url.replace("git@github.com:", "https://github.com/").replace(".git", "")
            logger.info(
                f"Check the full changelog at {github_url}/compare/{head_commit}...{git.repository.active_branch.name}"
            )

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

    def _reconcile_recorded_version(self) -> bool:
        """Reset the recorded version if it is ahead of the version currently running, which happens
        after switching release channel, checking out an older revision or downgrading odev.

        :return: Whether the recorded version was reset
        :rtype: bool
        """
        if version.parse(self.config.update.version) <= version.parse(self.version):
            return False

        recorded_version = string.stylize(self.config.update.version, "repr.version")
        logger.debug(f"Recorded version {recorded_version} is ahead of the current version, resetting it")
        self.config.update.version = self.version
        return True

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
        if self._reconcile_recorded_version():
            return

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
            from odev.commands.database.delete import DeleteCommand  # noqa: PLC0415
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

    def import_commands(self, sources: Iterable[Path]) -> list[tuple[type[CommandType], Path]]:
        """Import all commands from the source directories.

        :param sources: Source directories to search for commands.
        :return: List of imported command classes, paired with the module they were defined in
        :rtype: List[Tuple[CommandType, Path]]
        """
        command_modules = self.list_commands(sources)
        command_classes: list[tuple[type[CommandType], Path]] = []

        for module_info in command_modules:
            if not isinstance(module_info.module_finder, FileFinder):
                raise TypeError("Module finder is not a FileFinder instance")

            if module_info.ispkg:
                module_path = Path(module_info.module_finder.path) / module_info.name / "__init__.py"
            else:
                module_path = Path(module_info.module_finder.path) / f"{module_info.name}.py"

            spec = spec_from_file_location(module_info.name, module_path.as_posix())

            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module {module_info.name} from {module_path.as_posix()}")

            command_module: ModuleType = module_from_spec(spec)
            spec.loader.exec_module(command_module)
            command_classes.extend(
                (command[1], module_path) for command in inspect.getmembers(command_module, self.__filter_commands)
            )

        return command_classes

    def register_commands(self) -> None:
        """Register all commands from the commands directory."""
        for command_class, module_path in self.import_commands(self.commands_path.iterdir()) + self.import_commands(
            [self.commands_path]
        ):
            self.commands.register(command_class, module_path)

    def load_plugins(self) -> None:
        """Import all enabled plugins to allow them to patch the framework."""
        import odev  # noqa: PLC0415

        # Ensure odev.plugins exists as a module so legacy imports work
        plugins_module = sys.modules.get("odev.plugins")

        if plugins_module is None:
            plugins_module = ModuleType("odev.plugins")
            plugins_module.__package__ = "odev.plugins"
            plugins_module.__file__ = None
            plugins_module.__spec__ = ModuleSpec("odev.plugins", None, is_package=True)
            sys.modules["odev.plugins"] = plugins_module

            if hasattr(odev, "__path__"):
                odev.plugins = plugins_module

        # Always repoint the search path: a developer checkout may contain an `odev/plugins` symlink used for IDE
        # import resolution, making python resolve `odev.plugins` as a namespace package rooted at the repository.
        # The plugins directory configured for this run must win over it.
        plugins_module.__path__ = [str(self.plugins_path)]

        # Add plugins_path to sys.path to allow direct imports of plugin modules
        if str(self.plugins_path) not in sys.path:
            sys.path.insert(0, str(self.plugins_path))

        for plugin in self.plugins:
            logger.debug(
                f"Loading plugin {plugin.name!r} version {string.stylize(plugin.manifest['version'], 'repr.version')}"
            )

            try:
                self._load_plugin_module(plugin)
            except ModuleNotFoundError as error:
                logger.debug(f"Missing python package while loading plugin {plugin.name!r}: {error}")

                if not self._install_missing_plugin_requirements():
                    logger.error(
                        f"Could not load plugin module {plugin.module}: {error}\n"
                        "The missing package is not declared in the requirements of any enabled plugin, "
                        f"consider reporting this issue to the maintainer of plugin {plugin.name!r}"
                    )
                    continue

                try:
                    self._load_plugin_module(plugin)
                except Exception as retry_error:  # noqa: BLE001
                    logger.error(f"Could not load plugin module {plugin.module}: {retry_error}")
            except Exception as error:  # noqa: BLE001
                logger.error(f"Could not load plugin module {plugin.module}: {error}")

    def _load_plugin_module(self, plugin: Plugin) -> None:
        """Import a plugin module and register it under the `odev.plugins` namespace.

        :param plugin: Plugin whose module should be imported.
        """
        module_basename = plugin.module
        module_name = f"odev.plugins.{module_basename}"

        # Try to import directly from sys.path first
        try:
            module = importlib.import_module(module_basename)
        except ImportError:
            # Fallback to explicit file loading if direct import fails
            init_path = plugin.path / "__init__.py"
            if not init_path.exists():
                return
            spec = spec_from_file_location(module_basename, init_path)
            if not spec or not spec.loader:
                return
            module = module_from_spec(spec)
            sys.modules[module_basename] = module

            try:
                spec.loader.exec_module(module)
            except Exception:
                # Drop the half-initialized module so a later retry starts from a clean state
                sys.modules.pop(module_basename, None)
                raise

        # Ensure it's available as odev.plugins.X
        sys.modules[module_name] = module
        setattr(sys.modules["odev.plugins"], module_basename, module)

    def _install_missing_plugin_requirements(self) -> bool:
        """Install missing python packages from the requirements of all enabled plugins.

        Used to self-heal plugin imports failing on missing python packages, typically after the virtual
        environment was recreated without reinstalling plugin requirements. Runs at most once per process
        to avoid repeated pip invocations.

        :return: Whether missing packages were detected and an installation was attempted.
        """
        if self._plugin_requirements_checked:
            return False

        self.__class__._plugin_requirements_checked = True
        python_env = PythonEnv()
        plugins_missing_requirements = [
            plugin for plugin in self.plugins if any(python_env.missing_requirements(plugin.path, raise_if_error=False))
        ]

        if not plugins_missing_requirements:
            return False

        logger.warning("Missing python packages detected, installing requirements of enabled plugins")

        for plugin in plugins_missing_requirements:
            python_env.install_requirements(plugin.path)

        return True

    def register_plugin_commands(self) -> None:
        """Register commands for the plugins directories, pulling changes in plugins if an error arises while loading
        the commands.

        The usual cause of a plugin failing to load is a checkout left behind by an update of odev itself, hence the
        one retry after pulling the plugins. Whatever survives that retry is reported and skipped: a single broken
        plugin makes its own commands unavailable, not the whole of odev.
        """
        failures = self._register_plugin_commands(self.plugins)

        if not failures:
            return

        for plugin, error in failures:
            logger.error(f"Error while loading commands of plugin {plugin.name!r}: {error}")

        with progress.spinner("Updating plugins"):
            # A plugin can also fail because one of its dependencies is outdated, so all of them are refreshed and
            # not only the ones that failed.
            updated = [self._pull_plugin(plugin) for plugin in self.plugins]

        if not any(updated):
            return

        self._install_missing_plugin_requirements()

        for plugin, error in self._register_plugin_commands([plugin for plugin, _ in failures]):
            logger.error(
                f"Could not load commands of plugin {plugin.name!r} after updating: {error}\n"
                f"Fix the repository in {plugin.path.as_posix()} or delete the plugin with "
                f"'odev plugin --delete {plugin.name}'"
            )

    def _register_plugin_commands(self, plugins: Iterable[Plugin]) -> list[tuple[Plugin, Exception]]:
        """Register all commands from the given plugins.

        :param plugins: Plugins whose commands should be registered.
        :return: The plugins whose commands could not be imported, each paired with the error that stopped it
        :rtype: List[Tuple[Plugin, Exception]]
        """
        failures: list[tuple[Plugin, Exception]] = []

        for plugin in plugins:
            try:
                for command_class, module_path in self.import_commands(plugin.path.glob("commands/**")):
                    self.commands.patch(command_class, module_path)
            except Exception as error:  # noqa: BLE001
                failures.append((plugin, error))

        return failures

    def _pull_plugin(self, plugin: Plugin) -> bool:
        """Pull the latest changes of a plugin repository, as a recovery attempt after its commands failed to load.

        Only plugins following a standard branch are updated: a checkout in a detached state, on a branch without a
        remote counterpart or on a development branch belongs to whoever is working in it, and pulling it would at
        best fail and at worst rebase work in progress.

        :param plugin: Plugin to update.
        :return: Whether changes were pulled, making another attempt at loading the commands worthwhile
        :rtype: bool
        """
        git = GitConnector(plugin.name)
        repository = git.repository

        if repository is None:
            logger.warning(f"Repository for plugin {plugin.name!r} not found at {plugin.path.as_posix()}")
            return False

        if repository.head.is_detached:
            logger.warning(f"Not updating plugin {plugin.name!r}: its repository is in a detached HEAD state")
            return False

        branch = repository.active_branch
        remote_branch = branch.tracking_branch()

        if remote_branch is None:
            logger.warning(
                f"Not updating plugin {plugin.name!r}: its branch {branch.name!r} does not track a remote branch"
            )
            return False

        if branch.name not in self.__standard_branches(git):
            logger.warning(
                f"Not updating plugin {plugin.name!r}: it is running from the non-standard branch {branch.name!r}, "
                "assuming you are in development mode"
            )
            return False

        with Stash(repository):
            try:
                # The tracked ref, and not the local branch name, is what the remote knows this branch as.
                remote = repository.remote(remote_branch.remote_name)
                remote.fetch()
                remote.pull(remote_branch.remote_head, rebase=True)
            except (GitCommandError, ValueError) as error:
                logger.warning(f"Error while pulling latest changes for plugin {plugin.name!r}: {error}")
                return False

        return True

    def __standard_branches(self, git: GitConnector) -> set[str]:
        """List the branches of a repository odev is allowed to update on its own.

        :param git: Connector to the repository.
        :return: Names of the branches considered standard for this repository
        :rtype: Set[str]
        """
        default_branch: str | None = None

        try:
            default_branch = git.default_branch
        except Exception as error:  # noqa: BLE001
            # Resolving the default branch goes through the Github API, which the recovery path cannot depend on.
            logger.debug(f"Could not resolve the default branch of {git.name!r}: {error}")

        return {branch for branch in (default_branch, "main", "master", "beta") if branch}

    def _commands_fingerprint(self) -> list[Any]:
        """Compute a cheap signature of the command modules available to odev.

        Walking the command directories for their names and modification times costs a fraction of what importing
        them does, so the commands are only discovered again once one of them was added, removed, renamed or
        modified.

        :return: The odev version, the version of each enabled plugin, and the state of the command directories
        :rtype: List[Any]
        """
        modules: list[str] = []

        for commands_path in [self.commands_path, *(plugin.path / "commands" for plugin in self.plugins)]:
            modules.extend(
                f"{module_path.as_posix()}:{module_path.stat().st_mtime}" for module_path in commands_path.rglob("*.py")
            )

        return [
            self.version,
            {plugin.name: plugin.manifest["version"] for plugin in self.plugins},
            sha256("\n".join(sorted(modules)).encode()).hexdigest(),
        ]

    def _load_config(self) -> None:
        """Reload the configuration file."""
        self.__class__.config = Config(self.name)

    def _plugin_link(self, name: str) -> Path | None:
        """Find the link recording a plugin as installed.

        Every link is considered, not only the one at the conventional path, so a plugin that odev could not load
        still counts as installed and can be deleted, whatever name its link was given.

        :param name: Name of the plugin to look up
        :return: Path to the link, or `None` if the plugin is not installed
        """
        if (link := plugin_link(self._plugin_discovery(), name)) is not None:
            return link

        # A link pointing nowhere is not reported by the discovery, yet it is still installed and still holds the
        # module name, so look the conventional path up as well.
        plugin_path = self.plugins_path / plugin_module_name(name)
        return plugin_path if plugin_path.is_symlink() or plugin_path.is_dir() else None

    def _plugin_is_installed(self, name: str) -> bool:
        """Check whether a plugin is installed, that is whether it is linked under the plugins directory.

        :param name: Name of the plugin to check
        :return: Whether the plugin is installed
        """
        return self._plugin_link(name) is not None

    def install_plugin(self, plugin: str, as_dependency: bool = False) -> None:
        """Install a new plugin from a git repository.

        :param plugin: Git repository of the plugin to install
        :param as_dependency: Whether the plugin is being installed as a dependency of another plugin
        """
        plugin_path = self.plugins_path / plugin_module_name(plugin)

        if (plugin_path.is_symlink() or plugin_path.exists()) and plugin_identity(plugin_path.resolve()) != plugin:
            # The module name is what python imports a plugin as, so two plugins can never share one. The link
            # already being taken is the filesystem refusing the collision, which nothing else has to track, and
            # nothing is cloned before that is known.
            raise OdevError(
                f"Cannot install plugin {plugin!r}: another plugin already uses the module name "
                f"{plugin_path.name!r}, delete it first with "
                f"'odev plugin --delete {plugin_identity(plugin_path.resolve())}'"
            )

        with progress.spinner(f"Installing plugin{' dependency' if as_dependency else ''} {plugin!r}"):
            repository = GitConnector(plugin)
            revision = self.config.update.release if self.config.update.release in ["main", "beta"] else None

            if repository.exists:
                repository.update()
                if revision:
                    self.__checkout_release_channel(repository, revision)
            else:
                repository.clone(revision=revision)

            manifest = read_plugin_manifest(repository.path, plugin)

            if manifest is None:
                raise OdevError(
                    f"Repository {plugin!r} is not an odev plugin: it does not expose a {PLUGIN_MANIFEST_FILENAME} "
                    "declaring a '__version__'"
                )

            for dependency in manifest["depends"]:
                self.install_plugin(dependency, as_dependency=True)

            self.plugins_path.mkdir(parents=True, exist_ok=True)

            if self._plugin_is_installed(plugin):
                logger.info(f"Plugin {plugin!r} is already installed")
            else:
                try:
                    logger.debug(f"Creating symbolic link {plugin_path.as_posix()} to {repository.path.as_posix()}")
                    plugin_path.symlink_to(repository.path, target_is_directory=True)

                    # The link has to exist before the setup script runs: the configuration sections a plugin
                    # contributes are read from the links, and a setup script storing its own settings would have
                    # nowhere to write them otherwise. Anything failing below removes the link again, leaving no
                    # half-installed plugin behind.
                    self._forget_plugins()
                    self._load_config()
                    PythonEnv().install_requirements(repository.path)
                    self._setup_plugin(repository.path, plugin)
                except Exception as error:
                    plugin_path.unlink(missing_ok=True)
                    self._forget_plugins()
                    self._load_config()
                    raise OdevError(f"Error while installing plugin {plugin!r}: {error}") from error

                logger.info(f"Installed plugin{' dependency' if as_dependency else ''} {plugin!r}")

            self._forget_plugins()
            self._load_config()

    def delete_plugin(self, plugin: str) -> None:
        """Delete a plugin and the plugins that depend on it.

        Only the link making odev load the plugin is removed: the local clone is kept so enabling the plugin
        again never downloads it a second time.

        :param plugin: Name of the plugin to delete
        """
        if not self._plugin_is_installed(plugin):
            logger.info(f"Plugin {plugin!r} is not installed")
            return

        # Every installed plugin is considered, not only the ones odev could load: a plugin left out of this run
        # still depends on what its manifest declares, and its link would otherwise survive the plugin it needs.
        dependents = plugins_requiring(self._plugin_discovery().installed, plugin)

        if dependents:
            logger.warning(
                f"Deleting plugin {plugin!r} will also delete the following dependent plugins:\n"
                f"{string.join_bullet(dependents)}"
            )
        else:
            logger.warning(f"You are about to delete the plugin {plugin!r}")

        if not self.console.confirm("Do you want to continue?", default=False):
            raise OdevError("Aborting plugin deletion")

        with progress.spinner(f"Deleting plugin {plugin!r}"):
            for name in [plugin, *dependents]:
                link = self._plugin_link(name)

                if link is None:
                    continue

                if not (link.is_symlink() or link.is_file()):
                    # Only the link recording the plugin is ever removed. A real directory is someone's checkout,
                    # never something odev created, and deleting it would take their work with it.
                    logger.warning(
                        f"Plugin {name!r} is not a link but a directory at {link.as_posix()}, so it was left "
                        "untouched; move or remove it yourself to stop odev from loading it"
                    )
                    continue

                link.unlink()
                logger.info(f"Deleted plugin {name!r}")

            self._forget_plugins()
            self._load_config()

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

    def _instantiate_command(
        self,
        command_cls: type[CommandType],
        cli_args: Sequence[str],
        database: DatabaseType | None = None,
    ) -> tuple[CommandType, Sequence[str]]:
        """Instantiate a command with the given arguments and database.

        :param command_cls: Command class to instantiate.
        :param cli_args: Arguments to pass to the command.
        :param database: Database to pass to the command.
        :return: A tuple containing the instantiated command and the arguments used.
        """
        if database is None:
            arguments = self.parse_arguments(command_cls, *cli_args)
            return command_cls(arguments), cli_args

        cli_args = (database.name, *cli_args)
        arguments = self.parse_arguments(command_cls, *cli_args)

        if "database" in inspect.getfullargspec(command_cls.__init__).args:
            return command_cls(arguments, database=database), cli_args  # type: ignore [call-arg]

        return command_cls(arguments), cli_args

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

        command: CommandType | None = None
        telemetry = None
        command_errored: bool = False

        try:
            command, cli_args = self._instantiate_command(command_cls, cli_args, database=database)
            command._argv = cli_args
            logger.debug(f"Running {command!r}")
            self._command_stack.append(command)
            telemetry = self.telemetry.send(command)
            command.run()
        except OdevError as exception:
            command_errored = True
            logger.error(str(exception))
        else:
            if history:
                self.store.history.set(command)
        finally:
            if command is not None:
                if command in self._command_stack:
                    self._command_stack.pop()

                logger.debug(f"Cleaning up after {command!r}")
                command.cleanup()
                command.console.bypass_prompt = command._bypass_prompt_orig

                if telemetry is not None:
                    telemetry.finish(
                        exit_code=int(command_errored),
                        execution_time=(monotonic() - self.start_time) / 60,
                    )

        return not command_errored

    def dispatch(self, argv: list[str] | None = None) -> bool:
        """Handle commands and arguments as received from the terminal.
        :param argv: Optional list of command-line arguments used to override arguments received from the CLI.
        :return: True if the command were executed successfully, False otherwise.
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

        return self.run_command(argv[0], *argv[1:], history=True)

    def check_release(self) -> None:
        """Check if a new release is available."""
        if not self.git.repository or self.git.repository.head.is_detached:
            return

        if self.git.repository.active_branch.name != self.config.update.release:
            logger.warning(
                f"Release channel is set to {self.config.update.release!r} in configuration file "
                f"but repository is on branch {self.git.repository.active_branch.name!r}\n"
                "Consider running 'odev config update.release <branch>' to switch odev and its plugins to the desired "
                "release channel"
            )

    def update_available(self) -> bool:
        """Check whether newer changes are available for odev in its remote repository.

        Based on the remote tracking branch as of the last time changes were fetched by the periodic
        update check, this does not reach out to the network.

        :return: Whether newer changes are available
        :rtype: bool
        """
        if self.git.repository is None:
            return False

        return self.__git_branch_behind(self.git.repository)

    def switch_release_channel(self, branch: str) -> None:
        """Switch the release channel to the given branch."""
        with progress.spinner(f"Switching odev to {branch!r} release channel"):
            self.__checkout_release_channel(self.git, branch)

        with progress.spinner(f"Switching plugins to {branch!r} release channel"):
            for plugin in self.plugins:
                self.__checkout_release_channel(GitConnector(plugin.name), branch)

        self.config.update.release = branch
        self._set_version_after_update()
        self._reconcile_recorded_version()
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
            PythonEnv().install_requirements(repo.path)

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
        if repository.head.is_detached:
            return False

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

    def _should_update_now(self) -> bool:
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
