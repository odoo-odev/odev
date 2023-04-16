import inspect
from collections import abc
from configparser import ConfigParser, SectionProxy
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Iterator,
    List,
    Literal,
    MutableMapping,
    Optional,
    Union,
)


__all__ = ["Config"]


CONFIG_DIR: Path = Path.home() / ".config" / "odev"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ConfigSection(abc.MutableMapping):
    """Light wrapper around configparser section to write and retrieve
    key/value pairs.
    """

    def __init__(self, parser: "ConfigManager", name: str):
        """Light wrapper around configparser section to write and retrieve
        key/value pairs.
        """

        self.config: "ConfigManager" = parser
        """Config parser implementation."""

        self.name: str = name
        """Name of this config section."""

        if not self.config.parser.has_section(name):
            self.config.parser.add_section(name)

        self._section: SectionProxy = self.config.parser.__dict__["_sections"][name]
        """Config parser section implementation."""

    def set(self, key: str, value: Any):
        """Set a key/value pair."""
        self.__setitem__(key, value)

    def __getitem__(self, key: str, default: Optional[str] = None) -> str:
        if not self.config.parser.has_option(self.name, key):
            if default is not None:
                return default

            raise KeyError(f"{key!r} is not a valid key")

        return self.config.parser.get(self.name, key)

    def __setitem__(self, key: str, value: Any):
        self.config.parser.set(self.name, key, value)
        self.config.save()

    def __delitem__(self, key: str):
        del self._section[key]
        self.config.save()

    def __iter__(self) -> Iterator[str]:
        return iter(self._section.keys())

    def __len__(self) -> int:
        return len(self._section.keys())


class ConfigManager(abc.MutableMapping):
    """Light wrapper around configparser to write and retrieve
    configuration saved on disk.
    """

    sections: MutableMapping[str, ConfigSection] = {}
    """Config sections."""

    def __init__(self, name: str):
        """Light wrapper around configparser to write and retrieve
        configuration saved on disk.
        """

        self.name: str = name
        """Name of this config manager, also serves as the name of the file
        to save configuration to.
        """

        self.path: Path = CONFIG_DIR / f"{self.name}.cfg"
        """Path to the file containing configuration options,
        inferred from the name.
        """

        self.parser: ConfigParser = ConfigParser()
        """Config parser implementation."""

        self.load()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}, path={self.path!r})"

    def load(self):
        """Load the content of the config file, creating it if need be."""
        files_read = self.parser.read(self.path)

        if not files_read:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.path.touch(mode=0o600, exist_ok=True)
            return self.load()

        for section in self.parser.sections():
            self.sections[section] = ConfigSection(self, section)

    def reload(self):
        """Reload the content of the config file."""
        self.sections = {}
        self.load()

    def save(self):
        """Save the configuration file in its current state."""
        with open(self.path, "w") as file:
            self.parser.write(file)

        self.reload()

    def section(self, key: str) -> ConfigSection:
        """Get a section of the config."""
        if key not in self.sections:
            raise KeyError(f"{key!r} is not a valid section")

        return self.sections[key]

    def set(self, section: str, option: str, value: Any):
        """Set a value in the config."""
        self.section(section).set(option, value)

    # Signature doesn't match MutableMapping because we get an option, not a section
    def get(self, section: str, option: str, default: Optional[str] = None) -> str:  # type: ignore
        """Get a value from the config."""
        return self.section(section).get(option, default)

    def delete(self, section: str, option: str = None) -> bool:
        """Delete a value from the config."""
        if option is None:
            return self.parser.remove_section(section)

        return self.parser.remove_option(section, option)

    def __check_key(self, key: str):
        if "." not in key:
            raise KeyError(f"{key!r} is not a valid key, use format 'section.attribute'")

    def __getitem__(self, key: str) -> Union[ConfigSection, str]:
        self.__check_key(key)
        section, attribute = key.split(".", 1)
        return self.section(section).get(attribute)

    def __setitem__(self, key: str, value: Any):
        self.__check_key(key)
        section, attribute = key.split(".", 1)
        self.section(section).set(attribute, value)

    def __delitem__(self, key: str):
        self.__check_key(key)
        section, attribute = key.split(".", 1)
        del self.section(section)[attribute]

    def __iter__(self) -> Iterator[str]:
        return iter(self.sections.keys())

    def __len__(self) -> int:
        return len(self.sections.keys())


class Section:
    """Odev configuration section."""

    def __init__(self, name: str, config: "ConfigManager"):
        self._name: str = name
        """Name of this section."""

        self._config: "ConfigManager" = config
        """Configuration manager."""

    def __repr__(self) -> str:
        return f"Section({self._name!r})"

    def get(self, key: str, default: Optional[str] = None) -> str:
        """Get a value from this section."""
        return self._config.get(self._name, key, default)

    def set(self, key: str, value: Any):
        """Set a value in this section."""
        self._config.set(self._name, key, str(value))


class PathsSection(Section):
    """Odev paths configuration."""

    @property
    def repositories(self) -> Path:
        """Path to the directory where repositories will be saved to and read from.
        Git repositories will be cloned from GitHub and stored under this directory
        with the path `<directory>/<organization>/<name>`.
        """
        return Path(self.get("repositories", "~/odoo/repositories")).expanduser()

    @repositories.setter
    def repositories(self, value: Union[str, Path]):
        self.set("repositories", value.as_posix() if isinstance(value, Path) else value)

    @property
    def dumps(self) -> Path:
        """Path to the directory where dump files will be saved when downloaded.
        When using the dump command, downloaded files will be stored under this path.
        """
        return Path(self.get("dumps", "~/odoo/dumps")).expanduser()

    @dumps.setter
    def dumps(self, value: Union[str, Path]):
        self.set("dumps", value.as_posix() if isinstance(value, Path) else value)


class UpdateSection(Section):
    """Configuration for odev auto-updates."""

    @property
    def mode(self) -> Literal["ask", "always", "never"]:
        """Behavior to observe when an update is available, one of:
        - 'ask': Ask the user if they want to update
        - 'always': Update automatically
        - 'never': Never update
        """
        value = self.get("mode", "ask")
        assert value in (
            "ask",
            "always",
            "never",
        ), f"'update.mode' must be one of 'ask', 'always', 'never', got {value!r}"
        return value  # type: ignore

    @mode.setter
    def mode(self, value: Literal["ask", "always", "never"]):
        assert value in (
            "ask",
            "always",
            "never",
        ), f"'update.mode' must be one of 'ask', 'always', 'never', got {value!r}"
        self.set("mode", value)

    @property
    def date(self) -> datetime:
        """Last time available updates were checked for.
        You should not have to modify this value as it is updated automatically.
        """
        return datetime.strptime(self.get("date"), DATETIME_FORMAT)

    @date.setter
    def date(self, value: Union[str, datetime]):
        self.set("date", value.strftime(DATETIME_FORMAT) if isinstance(value, datetime) else value)

    @property
    def version(self) -> str:
        """The version of odev after the last update.
        Used to run upgrade scripts when updating.
        You should not have to modify this value as it is updated automatically.
        """
        return self.get("version", "0.0.0")

    @version.setter
    def version(self, value: str):
        self.set("version", value)

    @property
    def interval(self) -> int:
        """Interval between update checks in days.
        Updates will be checked for once every `interval` day(s).
        """
        return int(self.get("interval"))

    @interval.setter
    def interval(self, value: Union[str, int]):
        assert str(value).isdigit() and int(value) >= 0, f"'update.interval' must be a positive integer, got {value!r}"
        self.set("interval", int(value))


class Config:
    """Odev configuration."""

    def __init__(self, name: str):
        self.name: str = name
        """Name of this configuration."""

        self._config: "ConfigManager" = ConfigManager(self.name)
        """Configuration manager."""

        self.paths: PathsSection = PathsSection("paths", self._config)
        """Paths to filesystem directories or files used by odev."""

        self.update: UpdateSection = UpdateSection("update", self._config)
        """Configuration for odev auto-updates."""

    def sections(self) -> List[Section]:
        """Get all sections of this configuration."""
        return [value for _, value in inspect.getmembers(self, lambda v: isinstance(v, Section))]

    def dict(self) -> MutableMapping[str, MutableMapping[str, str]]:
        """Get a dictionary representation of this configuration."""
        sections: MutableMapping[str, MutableMapping[str, str]] = {section._name: {} for section in self.sections()}

        def is_property(v):
            return not inspect.isfunction(v) and not inspect.isbuiltin(v) and not inspect.ismethod(v)

        for section in sections:
            for key, value in inspect.getmembers(getattr(self, section), is_property):
                if not key.startswith("_"):
                    sections[section][key] = str(value)

        return sections
