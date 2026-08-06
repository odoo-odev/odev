import shutil
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from odev._version import __version__
from odev.common.commands import Command
from odev.common.odev import Manifest, Plugin, logger, parse_plugin_manifest, plugin_module_name

from tests.fixtures import CaptureOutput, OdevTestCase


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

        module_path = Path(__file__)

        with (
            self.assertRaises(ValueError) as error,
            self.patch(
                self.odev,
                "import_commands",
                return_value=[(FirstCommand, module_path), (SecondCommand, module_path)],
            ),
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

    def test_21_plugin_module_name(self):
        """The module name of a plugin should drop the organization and use underscores."""
        self.assertEqual(plugin_module_name("odoo-odev/odev-plugin-editor-base"), "odev_plugin_editor_base")
        self.assertEqual(plugin_module_name("odev-plugin-ai"), "odev_plugin_ai")

    def test_22_parse_plugin_manifest(self):
        """The manifest of a plugin should be parsed into its name, version, description and dependencies."""
        manifest = parse_plugin_manifest(
            '"""Some plugin."""\n\n__version__ = "1.2.3"\n\ndepends = ["test/test-plugin", 42]\n',
            "test/test-plugin-dep",
        )

        self.assertEqual(
            manifest,
            {
                "name": "test/test-plugin-dep",
                "version": "1.2.3",
                "description": "Some plugin.",
                "depends": ["test/test-plugin"],
            },
        )

    def test_23_parse_plugin_manifest_invalid(self):
        """A source that is not a valid plugin manifest should be rejected."""
        self.assertIsNone(parse_plugin_manifest('"""No version."""\n\ndepends = []\n', "test/test-plugin"))
        self.assertIsNone(parse_plugin_manifest("def invalid(:\n", "test/test-plugin"))
        self.assertIsNone(parse_plugin_manifest("__version__ = 1.0\n", "test/test-plugin"))
        self.assertIsNone(parse_plugin_manifest('{"name": "Sales", "version": "17.0"}\n', "test/test-addons"))

    def test_24_parse_plugin_manifest_does_not_execute_code(self):
        """Parsing the manifest of an untrusted repository should never execute its content."""
        with self.patch("odev.common.odev.logger", "warning") as logger_warning:
            manifest = parse_plugin_manifest(
                '"""Malicious plugin."""\n'
                "import odev.common.odev as target\n"
                'target.logger.warning("executed")\n'
                "raise SystemExit(1)\n"
                '__version__ = "6.6.6"\n',
                "evil/plugin",
            )

        self.assertEqual(
            manifest,
            {
                "name": "evil/plugin",
                "version": "6.6.6",
                "description": "Malicious plugin.",
                "depends": [],
            },
        )
        logger_warning.assert_not_called()
