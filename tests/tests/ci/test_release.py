import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase


RELEASE_SCRIPT = Path(__file__).parents[3] / ".github" / "scripts" / "release.py"

MANIFEST = """
# patch:  Patch version number, incremented when a bug is fixed
__version__ = "1.0.1"

depends = ["odev-plugin-editor-base"]
"""


def load_release_module() -> ModuleType:
    """Import the release tooling, which lives outside of any python package."""
    loader = SourceFileLoader("ci_release", RELEASE_SCRIPT.as_posix())
    module = module_from_spec(spec_from_loader(loader.name, loader))
    sys.modules[loader.name] = module
    loader.exec_module(module)

    return module


release = load_release_module()


class TestReleaseNextVersion(TestCase):
    """The next version should be derived from the prefixes of the commits to release."""

    def setUp(self):
        self.released = release.Version(4, 33, 0)

    def test_01_fixes_bump_patch(self):
        """Fixes, documentation and unknown prefixes should increment the patch number."""
        subjects = ["[FIX] git: keep the last line (#177)", "[DOC] commands: document flags", "no prefix at all"]
        version = release.next_version(self.released, self.released, subjects)
        self.assertEqual(str(version), "4.33.1")

    def test_02_improvements_bump_minor(self):
        """Improvements and features should increment the minor number and reset the patch number."""
        for prefix in ("IMP", "FEAT", "ADD", "imp"):
            with self.subTest(prefix=prefix):
                subjects = ["[FIX] git: keep the last line", f"[{prefix}] plugin: search plugins"]
                version = release.next_version(release.Version(4, 33, 4), release.Version(4, 33, 4), subjects)
                self.assertEqual(str(version), "4.34.0")

    def test_03_refactorings_bump_major(self):
        """Refactorings should increment the major number and reset the others."""
        subjects = ["[IMP] plugin: search plugins", "[REF] common: rework the store", "[FIX] git: pull"]
        version = release.next_version(self.released, self.released, subjects)
        self.assertEqual(str(version), "5.0.0")

    def test_04_single_bump_per_release(self):
        """The version should be incremented once, whatever the number of commits."""
        subjects = [f"[IMP] commands: improvement {index}" for index in range(5)]
        version = release.next_version(self.released, release.Version(4, 34, 0), subjects)
        self.assertEqual(str(version), "4.34.0")

    def test_05_level_raised_during_cycle(self):
        """A version bumped for fixes should be raised when an improvement lands afterwards."""
        subjects = ["[FIX] git: pull", "[REL] odev: bump the version to 4.33.1", "[IMP] plugin: search plugins"]
        version = release.next_version(self.released, release.Version(4, 33, 1), subjects)
        self.assertEqual(str(version), "4.34.0")

    def test_06_manual_bump_kept(self):
        """A version incremented by hand should not be lowered."""
        version = release.next_version(self.released, release.Version(5, 0, 0), ["[FIX] git: pull"])
        self.assertEqual(str(version), "5.0.0")

    def test_07_nothing_to_release(self):
        """No version should be computed when no change is waiting for a release."""
        self.assertIsNone(release.next_version(self.released, self.released, []))
        self.assertIsNone(release.next_version(self.released, self.released, ["[REL] odev: bump the version"]))

    def test_08_release_commits_ignored(self):
        """Commits of the release workflow alone should release the version they set."""
        version = release.next_version(self.released, release.Version(4, 34, 0), ["[REL] odev: bump the version"])
        self.assertEqual(str(version), "4.34.0")


class TestReleaseVersionFile(TestCase):
    """The version should be read from and written to the files of odev and its plugins."""

    def test_01_read_version(self):
        """The version should be read from the assignment, not from the comments around it."""
        self.assertEqual(release.read_version(MANIFEST), release.Version(1, 0, 1))

    def test_02_read_version_missing(self):
        """A file without a version should be reported."""
        with self.assertRaises(ValueError):
            release.read_version("depends = []\n")

    def test_03_write_version(self):
        """Only the version number should change in the file."""
        updated = release.write_version(MANIFEST, release.Version(1, 1, 0))
        self.assertEqual(updated, MANIFEST.replace("1.0.1", "1.1.0"))

    def test_04_bump_command(self):
        """The bump command should rewrite the version file in place."""
        with TemporaryDirectory() as directory:
            version_file = Path(directory) / "_version.py"
            version_file.write_text(RELEASE_SCRIPT.parents[2].joinpath("odev/_version.py").read_text())
            release.main(["bump", "--version-file", version_file.as_posix(), "--version", "9.8.7"])
            self.assertEqual(release.read_version(version_file.read_text()), release.Version(9, 8, 7))


class TestReleaseChangelog(TestCase):
    """The changelog should list the released commits by nature."""

    def test_01_grouped_by_prefix(self):
        """Commits should be grouped in sections, without their prefix and keeping their references."""
        changelog = release.changelog(
            [
                "[FIX] git: keep the last line (#177)",
                "[IMP] plugin: search plugins (#174)",
                "[REL] odev: bump the version to 4.34.0",
                "[ADD] database: change parameters",
                "[FIX] odoobin: read the repository name (#179)",
                "bump dependencies",
            ]
        )
        self.assertEqual(
            changelog,
            "### Features\n\n- database: change parameters\n\n"
            "### Improvements\n\n- plugin: search plugins (#174)\n\n"
            "### Fixes\n\n- git: keep the last line (#177)\n- odoobin: read the repository name (#179)\n\n"
            "### Other changes\n\n- bump dependencies",
        )

    def test_02_empty(self):
        """No changelog should be rendered when there is nothing to release."""
        self.assertEqual(release.changelog(["[REL] odev: bump the version to 4.34.0"]), "")
