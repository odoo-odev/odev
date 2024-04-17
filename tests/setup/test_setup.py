import shutil
from pathlib import Path

from tests.fixtures import OdevTestCase

from odev.setup import completion, directories, symlink, update


class TestSetupCompletion(OdevTestCase):

    def test_01_completion(self):
        """Test the setup script responsible of creating a symlink to the bash
        completion script of odev. A symlink should be created on the file system.
        """
        with self.patch(completion.console, "confirm", return_value=True):
            completion.setup(self.odev)

        self.assertTrue(Path("~/.local/share/bash-completion/completions/complete_odev.sh").expanduser().is_symlink())


class TestSetupSymlink(OdevTestCase):

    def test_01_symlink(self):
        """Test the setup script responsible of creating a symlink to odev.
        A symlink should be created to map the "odev" command to the main file
        of this application.
        """
        with self.patch(symlink.console, "confirm", return_value=True):
            symlink.setup(self.odev)

        self.assertTrue(Path("~/.local/bin/odev").expanduser().is_symlink())


class TestSetupDirectories(OdevTestCase):

    def test_01_directories_unchanged(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did not change, skip moving it.
        """
        with (
            self.patch(directories.logger, "debug") as mock_logger_debug,
            self.patch(directories.console, "directory", return_value=self.odev.config.paths.repositories),
            self.patch(directories.console, "confirm", return_value=True),
            self.patch(shutil, "move") as mock_move,
        ):
            directories.setup(self.odev)

        mock_logger_debug.assert_any_call(f"Directory {self.odev.config.paths.repositories} did not change, skipping")
        mock_move.assert_not_called()

    def test_02_directories_move(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the directory did change, move the old files to the new path and update
        the configuration file accordingly.
        """
        repositories_path = self.run_path / "repositories"
        repositories_path.mkdir(parents=True, exist_ok=True)
        self.odev.config.paths.repositories = repositories_path

        with (
            self.patch(directories.logger, "debug") as logger_debug,
            self.patch(directories.console, "directory", return_value=self.run_path / "new-repositories"),
            self.patch(directories.console, "confirm", return_value=True),
            self.patch(shutil, "move") as mock_move,
        ):
            directories.setup(self.odev)

        logger_debug.assert_any_call(f"Moving {repositories_path} to {self.odev.config.paths.repositories}")
        mock_move.assert_called_once()
        self.assertEqual(self.odev.config.paths.repositories, self.run_path / "new-repositories")

    def test_03_directories_empty(self):
        """Test the setup script responsible of registering the chosen directories
        to the configuration file creating the necessary paths on the file system.
        If the new directory already exists but is empty, it should be removed before
        it is recreated.
        """
        repositories_path = self.run_path / "repositories"
        repositories_path.mkdir(parents=True, exist_ok=True)
        (repositories_path / "test-file").touch()
        self.odev.config.paths.repositories = repositories_path

        new_repositories_path = self.run_path / "new-repositories"
        new_repositories_path.mkdir(parents=True, exist_ok=True)

        with (
            self.patch(directories.logger, "debug") as logger_debug,
            self.patch(directories.console, "directory", return_value=new_repositories_path.as_posix()),
            self.patch(directories.console, "confirm", return_value=True),
        ):
            directories.setup(self.odev)

        logger_debug.assert_any_call(f"Directory {new_repositories_path.as_posix()} exists but is empty, removing it")


class TestSetupUpdate(OdevTestCase):

    def test_01_update(self):
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
            update.setup(self.odev)

        self.assertEqual(self.odev.config.update.mode, "never", "should update the configuration file")
        self.assertEqual(self.odev.config.update.interval, 5, "should update the configuration file")
