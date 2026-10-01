import shutil
import tempfile
from pathlib import Path

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


class EditionDatabase:
    """Minimal stand-in for a database, exposing only the edition installed in it."""

    def __init__(self, edition: str):
        self.edition = edition


class TestForcedEdition(OdevTestCase):
    """`with_edition` forces the edition both ways, regardless of the one installed in the database."""

    def make_process(self, edition: str) -> OdoobinProcess:
        process = OdoobinProcess.__new__(OdoobinProcess)
        process.database = EditionDatabase(edition)  # type: ignore [assignment]
        process._forced_edition = None
        return process

    def repository_names(self, process: OdoobinProcess) -> list[str]:
        return [repository.name for repository in process.odoo_repositories]

    def test_defaults_to_the_database_edition(self):
        self.assertIn("odoo/enterprise", self.repository_names(self.make_process("enterprise")))
        self.assertNotIn("odoo/enterprise", self.repository_names(self.make_process("community")))

    def test_community_forced_on_an_enterprise_database(self):
        process = self.make_process("enterprise").with_edition("community")
        self.assertNotIn("odoo/enterprise", self.repository_names(process))

    def test_enterprise_forced_on_a_community_database(self):
        process = self.make_process("community").with_edition("enterprise")
        self.assertIn("odoo/enterprise", self.repository_names(process))
