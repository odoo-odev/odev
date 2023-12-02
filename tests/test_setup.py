import re
import shutil
from pathlib import Path
from uuid import uuid4

from odev.setup import completion, directories, symlink, update
from tests.fixtures import OdevTestCase


class TestSetup(OdevTestCase):
    @classmethod
    def tearDownClass(cls):
        if Path("/tmp/odev-tests").exists():
            shutil.rmtree("/tmp/odev-tests", ignore_errors=True)
        return super().tearDownClass()

    def test_setup_completion(self):
        """Test the setup script responsible of creating a symlink to the bash completion script of odev.
        A symlink should be created on the file system.
        """
        with (
            self.patch(completion.logger, "warning"),
            self.patch(completion.console, "confirm", return_value=True),
        ):
            completion.setup(self.odev.config)

        self.assertTrue(
            Path("~/.local/share/bash-completion/completions/complete_odev.sh").expanduser().is_symlink(),
            "should create a symlink to the bash completion script of odev",
        )

    def test_setup_symlink(self):
        """Test the setup script responsible of creating a symlink to odev.
        A symlink should be created to map the "odev" command to the main file of this application.
        """
        with (
            self.patch(symlink.logger, "warning"),
            self.patch(symlink.console, "confirm", return_value=True),
        ):
            symlink.setup(self.odev.config)

        self.assertTrue(Path("~/.local/bin/odev").expanduser().is_symlink(), "should create a symlink to odev")

    def test_setup_directories_skip_not_changed(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did not change, skip moving it.
        """
        with (
            self.patch(directories.logger, "warning"),
            self.patch(directories.logger, "debug") as mock_logger_debug,
            self.patch(directories.console, "directory", return_value=self.odev.config.paths.repositories),
            self.patch(directories.console, "confirm", return_value=True),
            self.patch(shutil, "move") as mock_move,
        ):
            directories.setup(self.odev.config)

        mock_logger_debug.assert_any_call(f"Directory {self.odev.config.paths.repositories} did not change, skipping")
        mock_move.assert_not_called()

    def test_setup_directories_move_old_to_new(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did change, move the old files to the new path and update the configuration file accordingly.
        """
        self.odev.config.paths.repositories = f"/tmp/odev-tests/{uuid4()}"
        old_path = self.odev.config.get("paths", "repositories")

        if not Path(old_path).exists():
            Path(old_path).mkdir(parents=True, exist_ok=True)

        with (
            self.patch(directories.logger, "warning"),
            self.patch(directories.logger, "debug") as logger_debug,
            self.patch(directories.console, "directory", return_value=f"/tmp/odev-tests/{uuid4()}"),
            self.patch(directories.console, "confirm", return_value=True),
            self.patch(shutil, "move") as mock_move,
        ):
            directories.setup(self.odev.config)

        logger_debug.assert_any_call(f"Moving {old_path} to {self.odev.config.paths.repositories}")
        mock_move.assert_called_once()
        file_re = r"/tmp/odev-tests/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
        self.assertIsNotNone(
            re.match(file_re, self.odev.config.paths.repositories.as_posix()), "should have a repositories path"
        )

    def test_setup_directories_remove_existing_empty(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the new directory already exists but is empty, it should be removed before it is recreated.
        """
        new_path = Path(f"/tmp/odev-tests/{uuid4()}")
        new_path.mkdir(parents=True, exist_ok=True)
        self.odev.config.paths.repositories = f"/tmp/odev-tests/{uuid4()}"
        self.odev.config.paths.repositories.mkdir(parents=True, exist_ok=True)
        (self.odev.config.paths.repositories / "test").touch(exist_ok=True)

        with (
            self.patch(directories.logger, "warning"),
            self.patch(directories.logger, "debug") as logger_debug,
            self.patch(directories.console, "directory", return_value=new_path.as_posix()),
            self.patch(directories.console, "confirm", return_value=True),
        ):
            directories.setup(self.odev.config)

        logger_debug.assert_any_call(f"Directory {new_path.as_posix()} exists but is empty, removing it")
        shutil.rmtree(new_path.as_posix(), ignore_errors=True)
        shutil.rmtree(self.odev.config.paths.repositories.as_posix(), ignore_errors=True)

    def test_setup_update(self):
        """Test the setup script responsible of setting the auto-update values for odev.
        The configuration file should be updated with the new values.
        """
        self.odev.config.reset("update")
        self.assertEqual(self.odev.config.update.mode, "ask", "should have a default value")
        self.assertEqual(self.odev.config.update.interval, 1, "should have a default value")

        with (
            self.patch(update.console, "select", return_value="never"),
            self.patch(update.console, "integer", return_value=5),
        ):
            update.setup(self.odev.config)

        self.assertEqual(self.odev.config.update.mode, "never", "should update the configuration file")
        self.assertEqual(self.odev.config.update.interval, 5, "should update the configuration file")
