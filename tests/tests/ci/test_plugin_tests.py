import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase


PLUGIN_TESTS_SCRIPT = Path(__file__).parents[3] / ".github" / "scripts" / "plugin_tests.py"

MANIFEST = """
\"\"\"Plugin description.\"\"\"

__version__ = "1.0.1"

depends = ["odoo-odev/odev-plugin-editor-base", "odoo-odev/odev-plugin-ai"]
"""


def load_plugin_tests_module() -> ModuleType:
    """Import the plugin tests tooling, which lives outside of any python package."""
    loader = SourceFileLoader("ci_plugin_tests", PLUGIN_TESTS_SCRIPT.as_posix())
    spec = spec_from_loader(loader.name, loader)

    if spec is None:
        raise ImportError(f"Cannot load {PLUGIN_TESTS_SCRIPT}")

    module = module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)

    return module


plugin_tests = load_plugin_tests_module()


class TestPluginTestsManifest(TestCase):
    """The dependencies of a plugin should be read from its manifest."""

    def test_01_module_name(self):
        """A plugin should be linked under the name odev imports it with."""
        self.assertEqual(
            plugin_tests.plugin_module_name("odoo-odev/odev-plugin-editor-vscode"), "odev_plugin_editor_vscode"
        )

    def test_02_dependencies(self):
        """Dependencies should be listed in the order they are declared."""
        self.assertEqual(
            plugin_tests.read_dependencies(MANIFEST),
            ["odoo-odev/odev-plugin-editor-base", "odoo-odev/odev-plugin-ai"],
        )

    def test_03_no_dependencies(self):
        """A manifest may declare no dependency, or not declare them at all."""
        self.assertEqual(plugin_tests.read_dependencies("depends = []"), [])
        self.assertEqual(plugin_tests.read_dependencies('__version__ = "1.0.0"'), [])


class TestPluginTestsSetup(TestCase):
    """A plugin and its dependencies should be linked into odev."""

    def setUp(self):
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root_path = Path(temporary_directory.name)
        self.fetched: list[str] = []

    def _add_plugin(self, name: str, depends: list[str] | None = None, requirements: bool = False) -> Path:
        """Create the repository of a plugin."""
        plugin_path = self.root_path / "repositories" / name
        plugin_path.mkdir(parents=True)

        if depends is not None:
            (plugin_path / "__manifest__.py").write_text(f"depends = {depends!r}\n")

        if requirements:
            (plugin_path / "requirements.txt").write_text("jinja2\n")

        return plugin_path

    def _fetch(self, name: str) -> Path:
        """Find the repository of a dependency, as if it had been cloned."""
        self.fetched.append(name)

        return self.root_path / "repositories" / name

    def test_01_resolve_without_dependencies(self):
        """A plugin without dependencies should be the only one resolved."""
        plugin_path = self._add_plugin("org/plugin", depends=[])

        self.assertEqual(
            plugin_tests.resolve_plugins("org/plugin", plugin_path, self._fetch), {"org/plugin": plugin_path}
        )
        self.assertEqual(self.fetched, [])

    def test_02_resolve_indirect_dependencies(self):
        """The dependencies of dependencies should be resolved too."""
        plugin_path = self._add_plugin("org/plugin", depends=["org/base"])
        base_path = self._add_plugin("org/base", depends=["org/core"])
        core_path = self._add_plugin("org/core")

        self.assertEqual(
            plugin_tests.resolve_plugins("org/plugin", plugin_path, self._fetch),
            {"org/plugin": plugin_path, "org/base": base_path, "org/core": core_path},
        )

    def test_03_resolve_circular_dependencies(self):
        """Plugins depending on each other should be fetched once."""
        plugin_path = self._add_plugin("org/plugin", depends=["org/base"])
        self._add_plugin("org/base", depends=["org/plugin", "org/base"])

        plugins = plugin_tests.resolve_plugins("org/plugin", plugin_path, self._fetch)

        self.assertEqual(list(plugins), ["org/plugin", "org/base"])
        self.assertEqual(self.fetched, ["org/base"])

    def test_04_link(self):
        """Plugins should be importable from the plugins directory of odev."""
        plugin_path = self._add_plugin("org/odev-plugin-example", depends=[])
        odev_path = self.root_path / "odev"

        links = plugin_tests.link_plugins({"org/odev-plugin-example": plugin_path}, odev_path)

        self.assertEqual(links, [odev_path / "odev" / "plugins" / "odev_plugin_example"])
        self.assertEqual(links[0].resolve(), plugin_path.resolve())
        self.assertTrue((links[0] / "__manifest__.py").is_file())

    def test_05_link_twice(self):
        """Linking again should replace the existing links."""
        plugin_path = self._add_plugin("org/odev-plugin-example", depends=[])
        other_path = self._add_plugin("org/other", depends=[])
        odev_path = self.root_path / "odev"

        plugin_tests.link_plugins({"org/odev-plugin-example": plugin_path}, odev_path)
        links = plugin_tests.link_plugins({"org/odev-plugin-example": other_path}, odev_path)

        self.assertEqual(links[0].resolve(), other_path.resolve())

    def test_06_requirements(self):
        """Only the requirements files that exist should be listed."""
        plugin_path = self._add_plugin("org/plugin", requirements=True)
        base_path = self._add_plugin("org/base")

        self.assertEqual(
            plugin_tests.requirements_files({"org/plugin": plugin_path, "org/base": base_path}),
            [plugin_path / "requirements.txt"],
        )
