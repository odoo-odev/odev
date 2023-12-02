"""Export data from a database and scaffold boilerplate code from templates."""

import json
from pathlib import Path
from typing import (
    Any,
    List,
    Mapping,
    MutableMapping,
    Union,
)

from odev.common.mixins.framework import OdevFrameworkMixin
from odev.common.version import OdooVersion


DEFAULT_CONFIG_SECTION = "default"


class CodeGeneratorConfig(OdevFrameworkMixin):
    """Configuration for the code exporter class."""

    config: MutableMapping[str, Any] = {}
    """The configuration for the code exporter as loaded from a JSON file."""

    def __init__(self, version: OdooVersion):
        """Initialize the code exporter configuration."""
        super().__init__()

        self.version: OdooVersion = version
        """The Odoo version to use within this configuration."""

        self.load()

    @property
    def path(self) -> Path:
        """Path to the configuration file."""
        return self.odev.static_path / "scaffold" / "config.json"

    @property
    def inherits(self) -> List[str]:
        """List of configuration versions this configuration inherits from.
        The first item in the list is the most basic version, the last item
        is the most specific version.

        i.e.: If the configuration for version `14.0` inherits from the
        configuration for version `13.0`, which inherits from the default
        configuration, the list will look like this:

        >>> ["default", "13.0", "14.0"]
        """
        inherits: List[str] = [str(self.version) if str(self.version) in self.config else DEFAULT_CONFIG_SECTION]
        inherit = self.config.get("inherit")

        while inherit is not None:
            inherits.append(inherit)
            inherit = self.config.get(inherit, {}).get("inherit")

        return list(reversed(inherits))

    def load(self) -> None:
        """Load the configuration from the JSON file and overrides
        values based on the current version used.
        """
        with self.path.open() as config_file:
            json_content: Mapping[str, MutableMapping[str, Any]] = json.load(config_file)

        base_config_key = str(self.version) if str(self.version) in json_content else DEFAULT_CONFIG_SECTION
        self.config = json_content.get(base_config_key, {})

        if "inherit" in self.config:
            inherits = self.inherits.copy()
            self.config = json_content[inherits.pop(0)]

            for inherit in inherits:
                self.__override(self.config, json_content.get(inherit, {}))

    def __override(self, base: MutableMapping[str, Any], new: Union[str, MutableMapping[str, Any]]) -> None:
        """Override the base configuration with the new configuration.
        :param base: The base configuration to override.
        :param new: The new configuration to override the base with.
        """
        for key, value in new.items():
            if isinstance(value, dict):
                self.__override(base[key], value)
            elif key in base:
                base[key] = value

    def __getitem__(self, key: str) -> Any:
        """Get an item from the configuration.
        :param key: The key to get from the configuration.
        """
        return self.config[key]

    def __iter__(self):
        return iter(self.config)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.path.as_posix()}, version={self.version!s})"
