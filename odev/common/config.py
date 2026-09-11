import inspect
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import (
    Literal,
    cast,
)

from odev._version import __version__
from odev.common.logging import logging
from odev.common.plugins import Plugin, installed_plugins


__all__ = ["Config"]


logger = logging.getLogger(__name__)


CONFIG_DIR: Path = Path.home() / ".config" / "odev"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
XGRAM_UNKNOWN = "<unknown>"
"""Marker stored in the configuration while the user's trigram has never been resolved."""


class Section:
    """Odev configuration section."""

    def __init__(self, name: str, config: "Config"):
        self.name: str = name
        """Name of this section."""

        self.config: Config = config
        """Configuration manager."""

        self.parser: ConfigParser = config.parser
        """Config parser implementation."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, path={self.config.path.as_posix()!r})"

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get an option from this section."""
        return self.parser.get(self.name, key, fallback=default)

    def set(self, key: str, value: str):
        """Set an option in this section."""
        self.parser.set(self.name, key, str(value))
        self.config.save()

    def reset(self, key: str):
        """Reset an option in this section to its default value."""
        self.config.reset(self.name, key)

    def delete(self, key: str):
        """Delete an option from this section."""
        self.config.delete(self.name, key)


class PathsSection(Section):
    """Odev paths configuration."""

    @property
    def repositories(self) -> Path:
        """Path to the directory where repositories will be saved to and read from.
        Git repositories will be cloned from GitHub and stored under this directory
        with the path `<directory>/<organization>/<name>`.
        Defaults to ~/odoo/repositories.
        """
        return Path(cast(str, self.get("repositories", "~/odoo/repositories"))).expanduser()

    @repositories.setter
    def repositories(self, value: str | Path):
        self.set("repositories", value.as_posix() if isinstance(value, Path) else value)

    @property
    def dumps(self) -> Path:
        """Path to the directory where dump files will be saved when downloaded.
        When using the dump command, downloaded files will be stored under this path.
        Defaults to ~/odoo/dumps.
        """
        return Path(cast(str, self.get("dumps", "~/odoo/dumps"))).expanduser()

    @dumps.setter
    def dumps(self, value: str | Path):
        self.set("dumps", value.as_posix() if isinstance(value, Path) else value)

    @property
    def upgrade(self) -> Path:
        """Path to the directory where Odoo Enterprise migration scripts are stored.
        Defaults to ~/odoo/repositories/odoo/upgrade.
        """
        return Path(cast(str, self.get("upgrade", "~/odoo/repositories/odoo/upgrade"))).expanduser()

    @upgrade.setter
    def upgrade(self, value: str | Path):
        self.set("upgrade", value.as_posix() if isinstance(value, Path) else value)


class UpdateSection(Section):
    """Configuration for odev auto-updates."""

    @classmethod
    def __check_mode(cls, mode: str | None):
        """Make sure the mode set in options is valid."""
        if mode not in ("ask", "always", "never"):
            raise ValueError(f"'update.mode' must be one of 'ask', 'always', 'never', got {mode!r}")

    @property
    def mode(self) -> Literal["ask", "always", "never"]:
        """Behavior to observe when an update is available, one of:
        - 'ask': Ask the user if they want to update
        - 'always': Update automatically
        - 'never': Never update
        Defaults to 'ask'.
        """
        value = self.get("mode", "ask")
        self.__check_mode(value)
        return cast(Literal["ask", "always", "never"], value)

    @mode.setter
    def mode(self, value: Literal["ask", "always", "never"]):
        self.__check_mode(value)
        self.set("mode", value)

    @property
    def date(self) -> datetime:
        """Last time available updates were checked for.
        You should not have to modify this value as it is updated automatically.
        """
        return datetime.strptime(cast(str, self.get("date", datetime.now().strftime(DATETIME_FORMAT))), DATETIME_FORMAT)

    @date.setter
    def date(self, value: str | datetime):
        self.set("date", value.strftime(DATETIME_FORMAT) if isinstance(value, datetime) else value)

    @property
    def version(self) -> str:
        """The version of odev after the last update.
        Used to run upgrade scripts when updating.
        You should not have to modify this value as it is updated automatically.
        """
        return cast(str, self.get("version", __version__))

    @version.setter
    def version(self, value: str):
        self.set("version", value)

    @property
    def interval(self) -> int:
        """Interval between update checks in days.
        Updates will be checked for once every `interval` day(s).
        Defaults to 1 day.
        """
        return int(cast(str, self.get("interval", "1")))

    @interval.setter
    def interval(self, value: str | int):
        if not str(value).isdigit() or int(value) < 0:
            raise ValueError(f"'update.interval' must be a positive integer, got {value!r}")

        self.set("interval", str(value))

    @property
    def release(self) -> str:
        """Release channel. You can switch between 'main' and 'beta' to get the latest features. Beta will have more
        updates but may be less stable. Defaults to 'main'.
        """
        return cast(str, self.get("release", "main"))

    @release.setter
    def release(self, value: str):
        self.set("release", value)


class PruningSection(Section):
    """Odev privacy configuration."""

    @property
    def date(self) -> datetime:
        """Last time local databases were pruned.
        You should not have to modify this value as it is updated automatically.
        """
        return datetime.strptime(cast(str, self.get("date", datetime.now().strftime(DATETIME_FORMAT))), DATETIME_FORMAT)

    @date.setter
    def date(self, value: str | datetime):
        self.set("date", value.strftime(DATETIME_FORMAT) if isinstance(value, datetime) else value)


class RepositoriesSection(Section):
    """Repositories configuration."""

    @property
    def date(self) -> datetime:
        """Last time repositories were pulled from GitHub.
        You should not have to modify this value as it is updated automatically.
        """
        return datetime.strptime(cast(str, self.get("date", datetime.now().strftime(DATETIME_FORMAT))), DATETIME_FORMAT)

    @date.setter
    def date(self, value: str | datetime):
        self.set("date", value.strftime(DATETIME_FORMAT) if isinstance(value, datetime) else value)

    def get_date(self, version: str) -> datetime:
        """Last time a specific version was pulled from GitHub."""
        value = self.get(f"date_{version}")
        if not value:
            return datetime.fromtimestamp(0)
        return datetime.strptime(value, DATETIME_FORMAT)

    def set_date(self, version: str, value: datetime):
        """Set the last time a specific version was pulled from GitHub."""
        self.set(f"date_{version}", value.strftime(DATETIME_FORMAT))
        self.date = value

    def is_pull_needed(self, version: str | None) -> bool:
        """Check whether a pull is needed for the given version."""
        if not version:
            return True

        return datetime.today() >= self.next_pull_date(version)

    @property
    def interval(self) -> int:
        """Interval between repository pull checks in days.\n        Pulls will be performed once every `interval` day(s).\n        Defaults to 7 days.\n"""
        return int(cast(str, self.get("interval", "7")))

    @interval.setter
    def interval(self, value: str | int):
        if not str(value).isdigit() or int(value) < 0:
            raise ValueError(f"'repositories.interval' must be a positive integer, got {value!r}")

        self.set("interval", str(value))

    def next_pull_date(self, version: str) -> datetime:
        """Get the next scheduled pull date for the given version."""
        pull_date = self.get_date(version)
        # Start of the week (Monday 00:00) of the last pull
        start_of_week = (pull_date - timedelta(days=pull_date.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Target date based on the interval
        next_pull = start_of_week + timedelta(days=self.interval)

        # If the interval is short or we've already passed the target day this week,
        # ensure the next pull is scheduled for the next period.
        if next_pull <= pull_date:
            return (pull_date + timedelta(days=self.interval)).replace(hour=0, minute=0, second=0, microsecond=0)

        return next_pull


class SecuritySection(Section):
    """Security configuration."""

    @property
    def encryption_key(self) -> str:
        """Encryption key."""
        return cast(str, self.get("encryption_key", ""))

    @encryption_key.setter
    def encryption_key(self, value: str):
        self.set("encryption_key", value)


class TelemetrySection(Section):
    """Telemetry configuration."""

    @property
    def client_id(self) -> str:
        """Unique client identifier."""
        return cast(str, self.get("client_id", ""))

    @client_id.setter
    def client_id(self, value: str):
        self.set("client_id", value)

    @property
    def enabled(self) -> bool:
        """Whether telemetry is enabled."""
        return self.get("enabled", "true") == "true"

    @enabled.setter
    def enabled(self, value: bool):
        self.set("enabled", "true" if value else "false")


class UserSection(Section):
    """Configuration about the developer running odev."""

    @property
    def xgram(self) -> str:
        """Odoo trigram of the current user, cached across runs.

        Resolving it requires a vault lookup and a call to git, which is too expensive to repeat on every command.
        An empty value means the user is known not to be an Odoo employee, `<unknown>` that the check never ran.
        """
        return cast(str, self.get("xgram", XGRAM_UNKNOWN))

    @xgram.setter
    def xgram(self, value: str):
        self.set("xgram", value)


class Config:
    """Odev configuration.
    Light wrapper around configparser to write and retrieve configuration values saved on disk.
    """

    parser: ConfigParser = ConfigParser()
    """Config parser implementation."""

    paths: PathsSection
    """Paths to filesystem directories or files used by odev."""

    update: UpdateSection
    """Configuration for odev auto-updates."""

    pruning: PruningSection
    """Configuration for odev pruning of databases."""

    telemetry: TelemetrySection
    """Configuration for odev telemetry."""

    repositories: RepositoriesSection
    """Configuration for Odoo repositories."""

    security: SecuritySection
    """Configuration for security and secrets encryption."""

    def __init__(self, name: str = "odev"):
        self.name: str = name
        """Name of this config manager, also serves as the name of the file
        to save configuration to.
        """

        self.__init_sections()
        self.load()
        self.fill_defaults()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, path={self.path!r})"

    @property
    def path(self) -> Path:
        """Path to the file containing configuration options, inferred from the name."""
        return CONFIG_DIR / f"{self.name}.cfg"

    def __init_sections(self):
        """Initialize all section attributes, including the ones contributed by the installed plugins."""
        modules = [inspect.getmodule(self)]

        for plugin in installed_plugins(CONFIG_DIR / "plugins").loaded:
            module = self.__import_plugin_config(plugin)

            if module is not None:
                modules.append(module)

        for module in modules:
            self.__add_sections(module)

    def __import_plugin_config(self, plugin: Plugin) -> ModuleType | None:
        """Import the `config.py` of a plugin, which contributes its own configuration sections.

        The plugins are read from the links under the plugins directory, the same source of truth the framework
        loads them from, so a plugin that is not installed never contributes a section. A plugin failing to import
        is reported and skipped: configuration is built before anything else, and one broken plugin must not keep
        odev from starting.

        :param plugin: The plugin to import the configuration of
        :return: The imported module, or `None` if the plugin has no configuration or it could not be imported
        """
        import importlib.util  # noqa: PLC0415 - avoid circular import

        config_path = plugin.path / "config.py"

        if not config_path.is_file():
            return None

        module_name = f"odev.plugins.{plugin.module}.config"
        spec = importlib.util.spec_from_file_location(module_name, config_path)

        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)

        try:
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as error:  # noqa: BLE001
            sys.modules.pop(module_name, None)
            logger.error(f"Could not load the configuration of plugin {plugin.name!r}: {error}")
            return None

        return module

    def __add_sections(self, module: ModuleType) -> None:
        """Add the configuration sections defined by a module.

        :param module: The module to read the `Section` subclasses from
        """
        for _, cls in inspect.getmembers(
            module, lambda member: inspect.isclass(member) and issubclass(member, Section) and member is not Section
        ):
            section = cls(getattr(cls, "_name", cls.__name__.replace("Section", "").lower()), self)

            if hasattr(self, section.name):
                logger.error(
                    f"Ignoring section {section.name!r} of {module.__name__}: a section by that name already exists"
                )
                continue

            setattr(self, section.name, section)

    def load(self):
        """Load the content of the config file, creating it if need be."""
        read_files = self.parser.read(self.path)

        if not read_files:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.path.touch(mode=0o600, exist_ok=True)
            self.load()

    def fill_defaults(self):
        """Fill the config file with default values."""
        for section_name, section in cast(
            list[tuple[str, Section]], inspect.getmembers(self, lambda member: isinstance(member, Section))
        ):
            if section_name not in self.parser.sections():
                self.parser.add_section(section_name)

            for option_name, option in cast(
                list[tuple[str, property]],
                inspect.getmembers(section.__class__, lambda member: isinstance(member, property)),
            ):
                if not self.parser.has_option(section_name, option_name):
                    option.fset(section, option.fget(section))

        self.save()

    def reload(self):
        """Reload the content of the config file."""
        self.sections = {}
        self.load()

    def save(self):
        """Save the configuration file in its current state."""
        with open(self.path, "w") as file:
            self.parser.write(file)

        self.reload()

    def check_attribute(self, section: str, option: str | None = None):
        """Ensure the given section and option exists."""
        if section not in self.parser.sections():
            raise KeyError(f"{section!r} is not a valid section in config {self.name!r}")
        if option is not None and option not in self.parser[section]:
            raise KeyError(f"{option!r} is not a valid option in section {section!r} of config {self.name!r}")

    def get(self, section: str, option: str, default: str | None = None) -> str | None:
        """Get a value from the config."""
        self.check_attribute(section, option)
        return self.parser.get(section, option, fallback=default)

    def set(self, section: str, option: str, value: str):
        """Set a value in the config."""
        self.check_attribute(section, option)
        self.parser.set(section, option, value)
        self.save()

    def reset(self, section: str, option: str | None = None):
        """Reset a value in the config to its default value."""
        self.delete(section, option)
        self.fill_defaults()
        self.save()

    def delete(self, section: str, option: str | None = None):
        """Delete a value from the config.
        Used for cleanup in upgrade scripts.
        """
        self.check_attribute(section, option)

        if option is None:
            self.parser.remove_section(section)
        else:
            self.parser.remove_option(section, option)

        self.save()

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Convert the config to a dict."""
        converted: dict[str, dict[str, str]] = self.parser.__dict__["_sections"].copy()
        cleaned: dict[str, dict[str, str]] = {}

        for section, options in converted.items():
            if not (section_obj := getattr(self, section, None)):
                continue

            cleaned[section] = {}

            for key in options:
                if not (option_obj := getattr(section_obj, key, None)):
                    continue

                if isinstance(option_obj, list):
                    options[key] = "\n".join(options[key].split(","))

                cleaned[section][key] = options[key]

        return cleaned
