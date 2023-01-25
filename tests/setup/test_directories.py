import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from odev.common.config import ConfigManager
from odev.setup.directories import logger, prompt, setup
from tests.fixtures import Patch


class TestSetupDirectories:
    @pytest.fixture(scope="session")
    def setup_config(self):
        """Fixture responsible of creating a configuration file with the default values."""
        path = Path("/tmp/odev-tests")
        path.mkdir(parents=True, exist_ok=True)

        with ConfigManager("test") as config:
            yield config

        shutil.rmtree(path, ignore_errors=True)
        config.path.unlink()

    def test_setup_directories_config_empty(self, setup_config):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        The configuration should be empty upon creation.
        """
        assert setup_config.get("paths", "odoo") is None
        assert setup_config.get("paths", "dev") is None

    def test_setup_directories_set_config(self, setup_config):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        Chosen directories should be registered in the configuration file.
        """
        with (
            Patch(logger, "warning"),
            Patch(prompt, "directory", side_effect=lambda m, d=None: f"/tmp/odev-tests/{uuid4()}"),
            Patch(prompt, "confirm", return_value=True),
        ):
            setup(setup_config)

        file_re = r"/tmp/odev-tests/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
        assert re.match(file_re, setup_config.get("paths", "odoo"))
        assert re.match(file_re, setup_config.get("paths", "dev"))

    def test_setup_directories_skip_not_changed(self, setup_config):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did not change, skip moving it.
        """
        keys = ["odoo", "dev"]
        with (
            Patch(logger, "warning"),
            Patch(logger, "debug") as logger_debug,
            Patch(prompt, "directory", side_effect=lambda m, d=None: setup_config.get("paths", keys.pop(0))),
            Patch(prompt, "confirm", return_value=True),
        ):
            setup(setup_config)

        logger_debug.assert_any_call(f"Directory {setup_config.get('paths', 'odoo')} did not change, skipping")

    def test_setup_directories_move_old_to_new(self, setup_config):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did change, move the old files to the new path.
        """
        old_path = setup_config.get("paths", "odoo")
        with (
            Patch(logger, "warning"),
            Patch(logger, "debug") as logger_debug,
            Patch(prompt, "directory", side_effect=lambda m, d=None: f"/tmp/odev-tests/{uuid4()}"),
            Patch(prompt, "confirm", return_value=True),
        ):
            setup(setup_config)

        logger_debug.assert_any_call(f"Moving {old_path} to {setup_config.get('paths', 'odoo')}")

    def test_setup_directories_remove_existing_empty(self, setup_config):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the new directory already exists but is empty, it should be removed.
        """
        dirs = ["odoo", "dev"]
        with (
            Patch(logger, "warning"),
            Patch(logger, "debug") as logger_debug,
            Patch(prompt, "directory", side_effect=lambda m, d=None: f"/tmp/odev-tests/{dirs.pop(0)}"),
            Patch(prompt, "confirm", return_value=True),
        ):
            Path("/tmp/odev-tests/dev").mkdir(parents=True, exist_ok=True)
            setup(setup_config)

        logger_debug.assert_any_call(f"Directory {setup_config.get('paths', 'dev')} is empty, removing it")