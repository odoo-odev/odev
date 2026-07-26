import shutil
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from odev._version import __version__
from odev.common.commands import Command
from odev.common.odev import Manifest, Odev, Plugin, logger

from tests.fixtures import CaptureOutput, OdevTestCase


REAL_UPDATE = Odev._update
"""Reference to the real implementation of `Odev._update`, taken before the test fixtures patch it away to
prevent tests from running git operations on the odev repository.
"""


class TestCommonOdev(OdevTestCase):
    """Global sanity check of the odev framework."""

    def test_01_config_file(self):
        """Config file should have been created in the correct directory."""
        self.assertEqual(self.odev.config.name, "odev-test")
        self.assertEqual(self.odev.config.path, Path.home() / ".config/odev/odev-test.cfg")

    def test_02_config_get_set_reset_delete(self):
        """Config manager should be able to get, set and reset values, as well as delete a key or a section.
        An error should be raised when accessing invalid values.
        """
        self.assertEqual(self.odev.config.update.version, __version__)
        self.odev.config.update.version = "1.0.0"
        self.assertEqual(self.odev.config.update.version, "1.0.0")
        self.odev.config.update.reset("version")
        self.assertEqual(self.odev.config.update.version, __version__)
        self.odev.config.update.delete("version")
        self.assertEqual(self.odev.config.parser.has_option("update", "version"), False)
        self.assertRaises(KeyError, self.odev.config.get, "invalid", "key")

    def test_03_restart(self):
        """The restart method should replace the current process."""
        with self.patch("os", "execv") as mock_execv:
            self.odev.restart()

        mock_execv.assert_called_once()

    def test_04_restart_on_update(self):
        """Odev should restart itself when updated."""
        with (
            self.patch(self.odev, "_should_update_now", return_value=True),
            self.patch(self.odev, "_update", return_value=True),
            self.patch(self.odev, "restart") as mock_restart,
        ):
            self.odev.commands.clear()
            self.odev._started = False
            self.odev.start()

        mock_restart.assert_called_once_with()

    def test_05_upgrade_same_version(self):
        """The upgrade method should do nothing if the version is the same as the current version."""
        with CaptureOutput() as output:
            self.odev.upgrade()

        self.assertEqual(output.stdout, "")
        self.assertEqual(self.odev.config.update.version, __version__)

    def test_06_upgrade_new_version(self):
        """The upgrade method should run upgrade scripts. with a version bigger than the current version.
        The version in the configuration file should be updated.
        """
        self.odev.config.update.version = "0.0.0"

        with CaptureOutput() as output:
            self.odev.upgrade()

        self.assertEqual(output.stdout, "Hello, odev!\n")
        self.assertEqual(self.odev.config.update.version, __version__)

    def test_07_register_duplicate(self):
        """An error should be raised if two commands share the same name."""

        class FirstCommand(Command):
            _name = "duplicate"

        class SecondCommand(Command):
            _name = "duplicate"

        with (
            self.assertRaises(ValueError) as error,
            self.patch(self.odev, "import_commands", return_value=[FirstCommand, SecondCommand]),
        ):
            self.odev.register_commands()

        self.assertEqual(error.exception.args[0], "Another command 'duplicate' is already registered")

    def test_08_dispatch_command(self):
        """The command should be dispatched based on the given name."""
        sys.argv = ["odev", "help"]
        help_command = self.odev.commands.get("help")

        with self.patch(help_command, "run") as mock_run:
            self.odev.dispatch()

        mock_run.assert_called_once_with()

    def test_09_dispatch_help_default(self):
        """The help command should be dispatched by default if no command was given."""
        sys.argv = ["odev"]
        help_command = self.odev.commands.get("help")

        with self.patch(help_command, "run") as mock_run:
            self.odev.dispatch()

        mock_run.assert_called_once_with()

    def test_10_dispatch_command_missing(self):
        """An error should be logged if the given command does not exist."""
        sys.argv = ["odev", "missing"]

        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()

        mock_error.assert_called_once_with("Command 'missing' not found")

    def test_11_dispatch_invalid_arguments(self):
        """An error should be logged if the given arguments are invalid."""
        sys.argv = ["odev", "help", "--invalid-argument"]

        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()

        mock_error.assert_called_once_with("Unrecognized arguments: --invalid-argument")

    def test_12_dispatch_command_error(self):
        """An error should be logged if the command raises an exception."""
        sys.argv = ["odev", "help", "invalid-command"]

        with self.patch(logger, "error") as mock_error:
            self.odev.dispatch()

        mock_error.assert_called_once_with("Cannot display help for inexistent command 'invalid-command'")

    def test_14_dispatch_version(self):
        """Odev should display its version when called with 'version' command."""
        sys.argv = ["odev", "version"]

        with CaptureOutput() as output:
            self.odev.dispatch()

        # VersionCommand output includes name, version, and release channel info
        self.assertIn(self.odev.version, output.stdout)
        self.assertIn(self.odev.name.capitalize(), output.stdout)

    def test_15_register_plugin_commands_retries_after_failure(self):
        """Plugin command registration should retry once after plugin updates."""
        with (
            self.patch_property(type(self.odev), "plugins", []),
            self.patch(
                self.odev, "_register_plugin_commands", side_effect=[RuntimeError("boom"), None]
            ) as register_mock,
            self.patch(logger, "error") as logger_error,
        ):
            self.odev.register_plugin_commands()

        self.assertEqual(register_mock.call_count, 2)
        logger_error.assert_called_once()

    def test_16_plugins_dependency_tree_cycle_raises(self):
        """Circular plugin dependencies should raise an explicit framework error."""
        cycle_root = self.run_path / "cycle-plugins"
        plugin_a = cycle_root / "test_plugin_cycle_a"
        plugin_b = cycle_root / "test_plugin_cycle_b"
        plugin_a.mkdir(parents=True, exist_ok=True)
        plugin_b.mkdir(parents=True, exist_ok=True)

        plugin_a_manifest = "__version__ = '1.0.0'\ndepends = ['cycle-plugins/test_plugin_cycle_b']\n"
        plugin_b_manifest = "__version__ = '1.0.0'\ndepends = ['cycle-plugins/test_plugin_cycle_a']\n"
        (plugin_a / "__manifest__.py").write_text(plugin_a_manifest)
        (plugin_b / "__manifest__.py").write_text(plugin_b_manifest)

        try:
            self.odev._plugins_dependency_tree.cache_clear()
            with (
                self.patch_property(type(self.odev), "plugins_path", cycle_root),
                self.assertRaisesRegex(Exception, "Circular dependency detected in plugins"),
            ):
                self.odev._plugins_dependency_tree()
        finally:
            shutil.rmtree(cycle_root, ignore_errors=True)

    def test_17_load_plugins_installs_missing_requirements_and_retries(self):
        """A plugin import failing on a missing python package should trigger a requirements install and a retry."""
        fake_manifest = Manifest(name="plugin", description="Test plugin", version="1.0.0", depends=[])
        fake_plugin = Plugin("test/plugin", Path("/nonexistent/test_plugin"), fake_manifest)

        with (
            self.patch_property(type(self.odev), "plugins", [fake_plugin]),
            self.patch(
                self.odev,
                "_load_plugin_module",
                side_effect=[ModuleNotFoundError("No module named 'fake_package'"), None],
            ) as load_mock,
            self.patch(self.odev, "_install_missing_plugin_requirements", return_value=True) as install_mock,
            self.patch(logger, "error") as logger_error,
        ):
            self.odev.load_plugins()

        self.assertEqual(load_mock.call_count, 2)
        install_mock.assert_called_once_with()
        logger_error.assert_not_called()

    def test_18_load_plugins_logs_error_when_requirements_complete(self):
        """A missing python package not declared in any plugin requirements should log an actionable error."""
        fake_manifest = Manifest(name="plugin", description="Test plugin", version="1.0.0", depends=[])
        fake_plugin = Plugin("test/plugin", Path("/nonexistent/test_plugin"), fake_manifest)

        with (
            self.patch_property(type(self.odev), "plugins", [fake_plugin]),
            self.patch(
                self.odev, "_load_plugin_module", side_effect=ModuleNotFoundError("No module named 'fake_package'")
            ) as load_mock,
            self.patch(self.odev, "_install_missing_plugin_requirements", return_value=False) as install_mock,
            self.patch(logger, "error") as logger_error,
        ):
            self.odev.load_plugins()

        self.assertEqual(load_mock.call_count, 1)
        install_mock.assert_called_once_with()
        logger_error.assert_called_once()
        self.assertIn("not declared in the requirements", logger_error.call_args.args[0])

    def test_19_register_plugin_commands_installs_requirements_on_retry(self):
        """Plugin command registration should install missing requirements before retrying after a failed import."""
        with (
            self.patch_property(type(self.odev), "plugins", []),
            self.patch(
                self.odev,
                "_register_plugin_commands",
                side_effect=[ModuleNotFoundError("No module named 'copier'"), None],
            ) as register_mock,
            self.patch(self.odev, "_install_missing_plugin_requirements") as install_mock,
            self.patch(logger, "error"),
        ):
            self.odev.register_plugin_commands()

        self.assertEqual(register_mock.call_count, 2)
        install_mock.assert_called_once_with()

    def test_20_load_plugins_repoints_preexisting_plugins_module(self):
        """An `odev.plugins` module resolved before plugins are loaded, as a developer checkout containing an
        `odev/plugins` symlink makes python do, should be repointed to the configured plugins directory.
        """
        stale_module = ModuleType("odev.plugins")
        stale_module.__path__ = [str(self.run_path / "stale-plugins")]

        with (
            self.patch_property(type(self.odev), "plugins", []),
            patch.dict(sys.modules, {"odev.plugins": stale_module}),
        ):
            self.odev.load_plugins()

            self.assertEqual(sys.modules["odev.plugins"].__path__, [str(self.odev.plugins_path)])

    def test_21_update_skipped_when_up_to_date(self):
        """Nothing should be pulled, and the user should not be prompted, when the local branch has no incoming
        changes left after fetching.
        """
        manifest = Manifest(name="odev", description="Odev", version=__version__, depends=[])

        with (
            self.patch("odev.common.odev", "Repo", return_value=MagicMock()),
            self.patch("odev.common.odev", "GitConnector", return_value=MagicMock()) as git_connector,
            self.patch(self.odev, "_load_plugin_manifest", return_value=manifest),
            self.patch(self.odev, "_Odev__git_branch_behind", return_value=False),
            self.patch(self.odev, "_Odev__update_prompt", return_value=True) as update_prompt,
        ):
            self.assertFalse(REAL_UPDATE(self.odev, self.odev.path))
            git_connector.return_value.fetch.assert_called_once_with(detached=False)

        update_prompt.assert_not_called()

    def test_22_update_records_check_date_when_up_to_date(self):
        """The date of the last update check should be recorded even when there was nothing to update, so that
        checks are not run again on every single command.
        """
        self.odev.config.update.date = "1995-12-21 00:00:00"

        with self.patch(self.odev, "_update", return_value=False):
            self.assertFalse(self.odev.update(restart=False))

        self.assertGreater(self.odev.config.update.date.year, 1995)

    def test_23_update_available(self):
        """An update should be reported only when the repository has incoming commits and none of its own."""
        for rev_list, expected in [("2\t0", True), ("0\t0", False), ("1\t3", False)]:
            repository = MagicMock(working_dir=str(self.odev.path))
            repository.head.is_detached = False
            repository.git.rev_list.return_value = rev_list

            with (
                self.subTest(rev_list=rev_list),
                self.patch_property(type(self.odev), "git", MagicMock(repository=repository)),
            ):
                self.assertEqual(self.odev.update_available(), expected)

    def test_24_update_available_without_repository(self):
        """No update should be reported when odev does not run from a git repository."""
        with self.patch_property(type(self.odev), "git", MagicMock(repository=None)):
            self.assertFalse(self.odev.update_available())

    def test_25_update_available_detached_head(self):
        """No update should be reported on a detached HEAD, which has no branch to compare with its remote."""
        repository = MagicMock(working_dir=str(self.odev.path))
        repository.head.is_detached = True

        with self.patch_property(type(self.odev), "git", MagicMock(repository=repository)):
            self.assertFalse(self.odev.update_available())

        repository.active_branch.tracking_branch.assert_not_called()

    def test_26_upgrade_version_ahead_of_current(self):
        """A recorded version ahead of the running one, as left over by a switch back from the 'beta' release
        channel, should be reset instead of being reported as a newer version forever.
        """
        self.odev.config.update.version = "999.0.0"

        with CaptureOutput() as output:
            self.odev.upgrade()

        self.assertEqual(output.stdout, "")
        self.assertEqual(self.odev.config.update.version, __version__)
