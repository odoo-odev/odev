"""Small mixin for adding framework specific properties to classes."""

from abc import ABC
from typing import TYPE_CHECKING, ClassVar


if TYPE_CHECKING:
    from odev.common.config import ConfigManager
    from odev.common.console import Console
    from odev.common.odev import Odev
    from odev.common.store import DataStore


class OdevFrameworkMixin(ABC):
    """Mixin for adding framework specific properties to classes."""

    _framework: ClassVar["Odev"]
    """The odev framework instance."""

    def __init__(self, *args, **kwargs):
        """Initialize the mixin."""
        super().__init__(*args, **kwargs)
        from odev.common import framework

        self.__class__._framework = framework

    @property
    def odev(self) -> "Odev":
        """The odev framework instance."""
        return self._framework

    @property
    def config(self) -> "ConfigManager":
        """Global configuration."""
        return self.odev.config

    @property
    def store(self) -> "DataStore":
        """Global data store."""
        return self.odev.store

    @property
    def console(self) -> "Console":
        """Console instance."""
        return self.odev.console
