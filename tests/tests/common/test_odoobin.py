import shutil
import tempfile
from pathlib import Path

from odev.commands.database.run import merge_modules_option
from odev.common.databases import Repository
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevTestCase


class FakeDatabase:
    """Minimal stand-in for a database, exposing only what the addons paths derivation reads."""

    def __init__(self, repository: Repository | None = None):
        self.repository = repository


class TestExpandAddonsPaths(OdevTestCase):
    """`expand_addons_paths` resolves a directory to the addons directories it contains."""

    @property
    def addons_path(self) -> Path:
        return self.res_path / "repositories" / "test" / "test-addons"

    def test_finds_modules_nested_in_subdirectories(self):
        expanded = OdoobinProcess.expand_addons_paths([self.addons_path])
        self.assertEqual(expanded, [self.addons_path, self.addons_path / "submodule"])

    def test_ignores_directories_without_modules(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(OdoobinProcess.expand_addons_paths([empty]), [])

    def test_deduplicates_overlapping_inputs(self):
        expanded = OdoobinProcess.expand_addons_paths([self.addons_path, self.addons_path / "submodule"])
        self.assertEqual(expanded, [self.addons_path, self.addons_path / "submodule"])

    def test_no_paths_yields_no_addons_paths(self):
        self.assertEqual(OdoobinProcess.expand_addons_paths([]), [])


class TestListAddons(OdevTestCase):
    """`list_addons` returns the names of the modules found recursively in a directory."""

    @property
    def addons_path(self) -> Path:
        return self.res_path / "repositories" / "test" / "test-addons"

    def test_lists_modules_nested_in_subdirectories(self):
        self.assertEqual(OdoobinProcess.list_addons([self.addons_path]), ["addon_01", "addon_02"])

    def test_deduplicates_overlapping_inputs(self):
        paths = [self.addons_path, self.addons_path / "submodule"]
        self.assertEqual(OdoobinProcess.list_addons(paths), ["addon_01", "addon_02"])

    def test_ignores_directories_without_modules(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(OdoobinProcess.list_addons([empty]), [])


class TestMergeModulesOption(OdevTestCase):
    """`merge_modules_option` gathers the modules passed to an odoo-bin option into a single occurrence."""

    def test_adds_option_when_missing(self):
        args = merge_modules_option(["--stop-after-init"], ("-i", "--init"), ["a", "b"])
        self.assertEqual(args, ["--stop-after-init", "-i", "a,b"])

    def test_merges_all_forms_of_the_option(self):
        args = merge_modules_option(["-i", "a", "--init=b", "-ic", "--dev=all"], ("-i", "--init"), ["d"])
        self.assertEqual(args, ["--dev=all", "-i", "a,b,c,d"])

    def test_deduplicates_modules(self):
        args = merge_modules_option(["--init", "a,b"], ("-i", "--init"), ["b", "c"])
        self.assertEqual(args, ["-i", "a,b,c"])

    def test_leaves_other_options_untouched(self):
        args = merge_modules_option(["-u", "a", "--i18n-overwrite"], ("-i", "--init"), ["b"])
        self.assertEqual(args, ["-u", "a", "--i18n-overwrite", "-i", "b"])

    def test_no_modules_leaves_arguments_untouched(self):
        self.assertEqual(merge_modules_option(["--dev=all"], ("-i", "--init"), []), ["--dev=all"])


class TestAdditionalAddonsPaths(OdevTestCase):
    """The addons paths derived from the linked repository must be expanded, and derived only once."""

    def setUp(self):
        super().setUp()
        self.odev.config.paths.repositories = self.res_path / "repositories"
        self.addons_path = self.res_path / "repositories" / "test" / "test-addons"

    def make_process(self, repository: Repository | None = None) -> OdoobinProcess:
        process = OdoobinProcess.__new__(OdoobinProcess)
        process.database = FakeDatabase(repository)  # type: ignore [assignment]
        process._additional_addons_paths = None
        return process

    def test_repository_is_expanded_to_its_addons_directories(self):
        """Regression for #98: the bare repository root is not a valid addons path when the
        modules live in subdirectories, so it must be expanded before being used.
        """
        process = self.make_process(Repository("test-addons", "test"))
        self.assertEqual(process.additional_addons_paths, [self.addons_path, self.addons_path / "submodule"])

    def test_without_repository_no_addons_paths(self):
        self.assertEqual(self.make_process().additional_addons_paths, [])

    def test_derived_only_once(self):
        process = self.make_process(Repository("test-addons", "test"))
        calls: list[object] = []
        original = OdoobinProcess.expand_addons_paths

        def counting_expand(paths):
            calls.append(paths)
            return original(paths)

        with self.patch(OdoobinProcess, "expand_addons_paths", side_effect=counting_expand):
            for _ in range(3):
                _ = process.additional_addons_paths

        self.assertEqual(len(calls), 1)

    def test_explicit_assignment_is_not_overridden(self):
        process = self.make_process(Repository("test-addons", "test"))
        process.additional_addons_paths = []
        self.assertEqual(process.additional_addons_paths, [])
