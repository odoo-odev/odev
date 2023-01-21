from pathlib import Path

from odev.common.config import ConfigManager


class TestCommonConfig:
    def setup_method(self):
        """Create a new config manager for each test."""
        self.config = ConfigManager("odev")

    def test_config_properties(self):
        """Config manager should have the right properties."""
        assert self.config.name == "odev", "name should be 'odev'"
        assert (
            self.config.path == Path.home() / ".config/odev/odev.cfg"
        ), "path should be 'odev.cfg' in the config directory"

    def test_config_file_exists(self):
        """Config file should exist."""
        assert self.config.path.exists(), "config file should exist"

    def test_config_set_get_delete_value(self):
        """Config manager should be able to set, get and delete a value."""
        self.config.set("test", "value", "test")
        assert self.config.get("test", "value") == "test", "should be able to set and get a value"
        self.config.delete("test", "value")
        assert self.config.get("test", "value") is None, "should be able to delete a value"
        self.config.delete("test")
        assert "test" not in self.config.sections(), "should be able to delete a section"
