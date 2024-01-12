import inspect
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import (
    List,
    Literal,
    Optional,
    Tuple,
    Union,
    cast,
)

from odev._version import __version__


__all__ = ["Config"]


CONFIG_DIR: Path = Path.home() / ".config" / "odev"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Section:
    """Odev configuration section."""

    def __init__(self, name: str, config: "Config"):
        self.name: str = name
        """Name of this section."""

        self.config: "Config" = config
        """Configuration manager."""

        self.parser: ConfigParser = config.parser
        """Config parser implementation."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, path={self.config.path.as_posix()!r})"

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
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
        return Path(self.get("repositories", "~/odoo/repositories")).expanduser()

    @repositories.setter
    def repositories(self, value: Union[str, Path]):
        self.set("repositories", value.as_posix() if isinstance(value, Path) else value)

    @property
    def dumps(self) -> Path:
        """Path to the directory where dump files will be saved when downloaded.
        When using the dump command, downloaded files will be stored under this path.
        Defaults to ~/odoo/dumps.
        """
        return Path(self.get("dumps", "~/odoo/dumps")).expanduser()

    @dumps.setter
    def dumps(self, value: Union[str, Path]):
        self.set("dumps", value.as_posix() if isinstance(value, Path) else value)


class UpdateSection(Section):
    """Configuration for odev auto-updates."""

    @classmethod
    def __check_mode(cls, mode: Optional[str]):
        """Make sure the mode set in options is valid."""
        assert mode in (
            "ask",
            "always",
            "never",
        ), f"'update.mode' must be one of 'ask', 'always', 'never', got {mode!r}"

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
        return datetime.strptime(self.get("date", datetime.now().strftime(DATETIME_FORMAT)), DATETIME_FORMAT)

    @date.setter
    def date(self, value: Union[str, datetime]):
        self.set("date", value.strftime(DATETIME_FORMAT) if isinstance(value, datetime) else value)

    @property
    def version(self) -> str:
        """The version of odev after the last update.
        Used to run upgrade scripts when updating.
        You should not have to modify this value as it is updated automatically.
        """
        return self.get("version", __version__)

    @version.setter
    def version(self, value: str):
        self.set("version", value)

    @property
    def interval(self) -> int:
        """Interval between update checks in days.
        Updates will be checked for once every `interval` day(s).
        Defaults to 1 day.
        """
        return int(self.get("interval", "1"))

    @interval.setter
    def interval(self, value: Union[str, int]):
        assert str(value).isdigit() and int(value) >= 0, f"'update.interval' must be a positive integer, got {value!r}"
        self.set("interval", str(value))


class PluginsSection(Section):
    """Odev plugins configuration."""

    @property
    def enabled(self) -> List[str]:
        """List of enabled plugins repositories.
        Defaults to an empty list.
        """
        return self.get("enabled", "odoo-ps/ps-tech-odev-plugin").split(",")

    @enabled.setter
    def enabled(self, value: Union[str, List[str]]):
        self.set("enabled", ",".join(value) if isinstance(value, list) else value)


class Config:
    """Odev configuration.
    Light wrapper around configparser to write and retrieve configuration values saved on disk.
    """

    def __init__(self, name: str = "odev"):
        self.name: str = name
        """Name of this config manager, also serves as the name of the file
        to save configuration to.
        """

        self.parser: ConfigParser = ConfigParser()
        """Config parser implementation."""

        self.paths: PathsSection = PathsSection("paths", self)
        """Paths to filesystem directories or files used by odev."""

        self.update: UpdateSection = UpdateSection("update", self)
        """Configuration for odev auto-updates."""

        self.plugins: PluginsSection = PluginsSection("plugins", self)
        """Configuration for odev plugins."""

        self.load()
        self.fill_defaults()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, path={self.path!r})"

    @property
    def path(self) -> Path:
        """Path to the file containing configuration options, inferred from the name."""
        return CONFIG_DIR / f"{self.name}.cfg"

    def load(self):
        """Load the content of the config file, creating it if need be."""
        read_files = self.parser.read(self.path)

        if not read_files:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.path.touch(mode=0o600, exist_ok=True)
            return self.load()

    def fill_defaults(self):
        """Fill the config file with default values."""
        for section_name, section in cast(
            List[Tuple[str, Section]], inspect.getmembers(self, lambda member: isinstance(member, Section))
        ):
            if section_name not in self.parser.sections():
                self.parser.add_section(section_name)

            for option_name, option in cast(
                List[Tuple[str, property]],
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

    def check_attribute(self, section: str, option: Optional[str] = None):
        """Ensure the given section and option exists."""
        if section not in self.parser.sections():
            raise KeyError(f"{section!r} is not a valid section in config {self.name!r}")
        if option is not None and option not in self.parser[section]:
            raise KeyError(f"{option!r} is not a valid option in section {section!r} of config {self.name!r}")

    def get(self, section: str, option: str, default: Optional[str] = None) -> str:
        """Get a value from the config."""
        self.check_attribute(section, option)
        return self.parser.get(section, option, fallback=default)

    def set(self, section: str, option: str, value: str):
        """Set a value in the config."""
        self.check_attribute(section, option)
        self.parser.set(section, option, value)
        self.save()

    def reset(self, section: str, option: Optional[str] = None):
        """Reset a value in the config to its default value."""
        self.delete(section, option)
        self.fill_defaults()
        self.save()

    def delete(self, section: str, option: Optional[str] = None):
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
        return self.parser.__dict__["_sections"]
