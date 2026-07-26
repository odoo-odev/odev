"""Tests for the python and system packages odev needs to prepare an Odoo installation."""

from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock, patch

from packaging.requirements import Requirement
from packaging.version import Version

from odev.common import system
from odev.common.odoobin import DEBIAN_INSTALL_SCRIPT, SETUPTOOLS_REQUIREMENT, OdoobinProcess
from odev.common.python import PythonEnv

from tests.fixtures import OdevTestCase


class TestSetuptoolsRequirement(OdevTestCase):
    """Guardrails for #93 and for the Odoo versions that cannot run on a recent setuptools."""

    def setuptools_requirement(self, python_version: str) -> Requirement:
        """Return the setuptools requirement that applies to a given python version."""
        text = (self.odev.static_path / "requirements.txt").read_text(encoding="utf-8")
        requirements = [
            Requirement(stripped)
            for line in text.splitlines()
            if (stripped := line.split("#", 1)[0].strip()) and Requirement(stripped).name == "setuptools"
        ]
        return next(
            requirement
            for requirement in requirements
            if requirement.marker is None or requirement.marker.evaluate({"python_version": python_version})
        )

    def test_modern_python_requires_a_usable_pep517_backend(self):
        """Setuptools 58 and 59 cannot load `setuptools.build_meta` for current pip, which is what
        breaks installing gevent with `--no-build-isolation`.
        """
        specifier = self.setuptools_requirement("3.10").specifier
        self.assertFalse(specifier.contains(Version("58.0.0")), "regression of #93")
        self.assertFalse(specifier.contains(Version("59.0.0")), "regression of #93")
        self.assertTrue(specifier.contains(Version("69.0.0")))

    def test_modern_python_excludes_setuptools_without_pkg_resources(self):
        """Setuptools 82 removed `pkg_resources`, which Odoo 15.0 and 16.0 import unconditionally
        in `odoo/modules/module.py`; both run on python 3.10.
        """
        specifier = self.setuptools_requirement("3.10").specifier
        self.assertTrue(specifier.contains(Version("81.2.0")))
        self.assertFalse(specifier.contains(Version("82.0.0")))
        self.assertFalse(specifier.contains(Version("83.0.0")))

    def test_legacy_python_keeps_the_legacy_cap(self):
        """Odoo 13.0 and older run on python 3.7 or 2.7, where setuptools must stay old."""
        specifier = self.setuptools_requirement("3.7").specifier
        self.assertTrue(specifier.contains(Version("57.5.0")))
        self.assertFalse(specifier.contains(Version("69.0.0")))

    def test_constant_matches_the_static_requirements(self):
        self.assertEqual(
            Requirement(SETUPTOOLS_REQUIREMENT).specifier,
            self.setuptools_requirement("3.10").specifier,
        )


class TestMissingRequirements(OdevTestCase):
    """`missing_requirements` must honour the full specifier and the markers of a requirement."""

    def write_requirements(self, *lines: str) -> Path:
        path = self.run_path / "requirements.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def missing(self, requirement: str, installed: dict[str, Version], python_version: str = "3.10") -> list[str]:
        venv = PythonEnv(str(self.run_path / "venv"))
        path = self.write_requirements(requirement)

        with (
            self.patch(PythonEnv, "installed_packages", return_value=installed),
            self.patch_property(PythonEnv, "version", python_version),
        ):
            return list(venv.missing_requirements(path))

    def test_upper_bound_is_honoured(self):
        """The requirement parser only kept the first operator of a specifier, so an upper bound
        was silently dropped and an over-new package was considered satisfied.
        """
        requirement = "setuptools>=69.0.0,<82; python_version >= '3.8'"
        self.assertEqual(self.missing(requirement, {"setuptools": Version("83.0.0")}), [requirement])
        self.assertEqual(self.missing(requirement, {"setuptools": Version("75.0.0")}), [])

    def test_lower_bound_is_honoured(self):
        requirement = "setuptools>=69.0.0,<82; python_version >= '3.8'"
        self.assertEqual(self.missing(requirement, {"setuptools": Version("58.0.0")}), [requirement])

    def test_marker_is_evaluated_for_the_environment_python(self):
        """Markers apply to the python of the virtual environment, not to the one odev runs under."""
        requirement = "setuptools<58.0.0; python_version < '3.8'"
        self.assertEqual(self.missing(requirement, {"setuptools": Version("69.0.0")}, python_version="3.10"), [])
        self.assertEqual(
            self.missing(requirement, {"setuptools": Version("69.0.0")}, python_version="3.7"),
            [requirement],
        )

    def test_missing_package_is_reported(self):
        self.assertEqual(self.missing("phonenumbers", {}), ["phonenumbers"])

    def test_unpinned_installed_package_is_satisfied(self):
        self.assertEqual(self.missing("phonenumbers", {"phonenumbers": Version("8.13.0")}), [])

    def test_comments_and_blank_lines_are_skipped(self):
        self.assertEqual(self.missing("# just a comment", {}), [])


class TestSatisfies(OdevTestCase):
    """`PythonEnv.satisfies` answers whether an installed package matches a specification."""

    def satisfies(self, specification: str, installed: dict[str, Version]) -> bool:
        venv = PythonEnv(str(self.run_path / "venv"))

        with self.patch(PythonEnv, "installed_packages", return_value=installed):
            return venv.satisfies(specification)

    def test_within_bounds(self):
        self.assertTrue(self.satisfies(SETUPTOOLS_REQUIREMENT, {"setuptools": Version("75.0.0")}))

    def test_below_lower_bound(self):
        self.assertFalse(self.satisfies(SETUPTOOLS_REQUIREMENT, {"setuptools": Version("58.0.0")}))

    def test_above_upper_bound(self):
        self.assertFalse(self.satisfies(SETUPTOOLS_REQUIREMENT, {"setuptools": Version("83.0.0")}))

    def test_not_installed(self):
        self.assertFalse(self.satisfies(SETUPTOOLS_REQUIREMENT, {}))


class TestSystemDependencies(OdevTestCase):
    """The system dependencies check must work on any unix and never install anything itself."""

    def setUp(self):
        super().setUp()
        self.odoo_path = self.run_path / "odoo"
        (self.odoo_path / "setup").mkdir(parents=True, exist_ok=True)
        self.process = OdoobinProcess.__new__(OdoobinProcess)
        self.process._framework = self.odev

    def write_script(self):
        (self.odoo_path / DEBIAN_INSTALL_SCRIPT).write_text("#!/bin/sh\n", encoding="utf-8")

    def missing(
        self,
        platform: str = "linux",
        on_path: Sequence[str] = (),
        debian_packages: list[str] | None = None,
        headers: bool = True,
    ) -> list[str]:
        """Return the names of the dependencies reported as missing on a simulated system.

        :param platform: The value of `sys.platform` to simulate.
        :param on_path: The executables available on the `PATH`.
        :param debian_packages: The packages Odoo declares and that are missing, None on a system
            where they cannot be listed.
        :param headers: Whether the interpreter ships its development headers.
        """
        venv = MagicMock(exists=True, version="3.10", has_development_headers=headers)

        with (
            self.patch_property(OdoobinProcess, "odoo_path", self.odoo_path),
            self.patch_property(OdoobinProcess, "venv", venv),
            self.patch(OdoobinProcess, "missing_debian_packages", return_value=debian_packages),
            patch("odev.common.odoobin.sys.platform", platform),
            patch("odev.common.system.shutil.which", side_effect=lambda command: command in on_path or None),
        ):
            return [dependency.name for dependency in self.process.missing_system_dependencies()]

    def test_probes_run_where_odoo_lists_no_package(self):
        """Regression guard: a system that is not Debian-based used to be reported as complete, and
        the user only found out when the build of gevent failed in the compiler.
        """
        self.assertEqual(
            self.missing(platform="darwin"),
            [system.C_COMPILER.name, system.POSTGRESQL_HEADERS.name],
        )

    def test_probes_are_satisfied_by_any_of_their_commands(self):
        self.assertEqual(self.missing(platform="darwin", on_path=["clang"]), [system.POSTGRESQL_HEADERS.name])
        self.assertEqual(self.missing(platform="darwin", on_path=["clang", "pg_config"]), [])

    def test_packages_declared_by_odoo_take_over_the_probes(self):
        self.assertEqual(self.missing(debian_packages=["libpq-dev", "libsasl2-dev"]), ["libpq-dev", "libsasl2-dev"])

    def test_headers_are_checked_even_where_odoo_lists_its_packages(self):
        """`debian/control` asks for `python3-dev`, not for the headers of the version of python the
        Odoo installation is actually built against.
        """
        self.assertEqual(self.missing(debian_packages=[], headers=False), [system.PYTHON_HEADERS.name])

    def test_no_check_outside_unix(self):
        self.assertEqual(self.missing(platform="win32", headers=False), [])

    def test_nothing_reported_on_a_complete_system(self):
        self.assertEqual(self.missing(debian_packages=[]), [])

    def test_never_installs_anything(self):
        """The machine odev runs on belongs to the user: the check reports and never escalates."""
        run, execute = MagicMock(), MagicMock()
        venv = MagicMock(exists=True, version="3.10", has_development_headers=False)

        with (
            self.patch_property(OdoobinProcess, "venv", venv),
            self.patch(
                OdoobinProcess,
                "missing_system_dependencies",
                return_value=[system.C_COMPILER, system.POSTGRESQL_HEADERS],
            ),
            patch("odev.common.odoobin.bash.run", run),
            patch("odev.common.odoobin.bash.execute", execute),
        ):
            self.process.check_system_dependencies()

        run.assert_not_called()
        execute.assert_not_called()

    def test_nothing_happens_when_no_dependency_is_missing(self):
        run = MagicMock()

        with (
            self.patch(OdoobinProcess, "missing_system_dependencies", return_value=[]),
            patch("odev.common.odoobin.bash.run", run),
        ):
            self.process.check_system_dependencies()

        run.assert_not_called()
