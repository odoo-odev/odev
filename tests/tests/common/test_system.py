"""Tests for the description of the operating system odev runs on."""

from collections.abc import Sequence
from unittest.mock import patch

from odev.common import system
from odev.common.system import SystemDependency

from tests.fixtures import OdevTestCase


class TestPackageManager(OdevTestCase):
    """Odev has to recognize the package manager of the system it runs on, whichever it is."""

    def package_manager(self, on_path: Sequence[str]) -> str | None:
        with patch("odev.common.system.shutil.which", side_effect=lambda command: command in on_path or None):
            return system.package_manager()

    def test_every_known_package_manager_is_detected(self):
        for manager in system.PACKAGE_MANAGERS:
            self.assertEqual(self.package_manager([manager]), manager)

    def test_the_package_manager_of_the_distribution_wins_over_homebrew(self):
        """Homebrew installs on Linux too, but a Fedora machine has to be told about `dnf`."""
        self.assertEqual(self.package_manager(["dnf", "brew"]), "dnf")

    def test_unknown_package_manager(self):
        self.assertIsNone(self.package_manager([]))


class TestInstallInstructions(OdevTestCase):
    """Whatever the system, the user must be told what is missing; the command is a bonus."""

    def instructions(self, dependencies: Sequence[SystemDependency], on_path: Sequence[str] = ()) -> str:
        with patch("odev.common.system.shutil.which", side_effect=lambda command: command in on_path or None):
            return system.install_instructions(dependencies, version="3.10")

    def test_names_and_command(self):
        instructions = self.instructions([system.C_COMPILER, system.POSTGRESQL_HEADERS], on_path=["dnf"])
        self.assertIn("• a C compiler", instructions)
        self.assertIn("• the PostgreSQL client headers (pg_config)", instructions)
        self.assertIn("sudo dnf install -y gcc libpq-devel", instructions)

    def test_placeholders_are_expanded(self):
        instructions = self.instructions([system.PYTHON_HEADERS], on_path=["apt-get"])
        self.assertIn("• the development headers of python 3.10 (Python.h)", instructions)
        self.assertIn("sudo apt-get install -y python3.10-dev", instructions)

    def test_names_only_without_a_known_package_manager(self):
        """On a system odev knows nothing about, saying what is missing is still useful."""
        instructions = self.instructions([system.C_COMPILER])
        self.assertEqual(instructions, "• a C compiler")

    def test_dependencies_without_a_package_are_still_named(self):
        """Arch Linux ships the python headers within `python` itself: there is nothing to install,
        but the user still has to know they are what is missing.
        """
        instructions = self.instructions([system.PYTHON_HEADERS, system.C_COMPILER], on_path=["pacman"])
        self.assertIn("• the development headers of python 3.10 (Python.h)", instructions)
        self.assertIn("sudo pacman -S --needed base-devel", instructions)
        self.assertNotIn("python3.10", instructions.rsplit("\n", 1)[-1])

    def test_no_command_when_nothing_can_be_named(self):
        instructions = self.instructions([system.PYTHON_HEADERS], on_path=["pacman"])
        self.assertEqual(instructions, "• the development headers of python 3.10 (Python.h)")


class TestSystemDependencyProbes(OdevTestCase):
    """A dependency is only ever reported as missing when it can be proven to be."""

    def found(self, dependency: SystemDependency, on_path: Sequence[str]) -> bool:
        with patch("odev.common.system.shutil.which", side_effect=lambda command: command in on_path or None):
            return dependency.found

    def test_any_command_proves_the_dependency(self):
        self.assertTrue(self.found(system.C_COMPILER, ["clang"]))
        self.assertTrue(self.found(system.C_COMPILER, ["gcc"]))
        self.assertFalse(self.found(system.C_COMPILER, ["pg_config"]))

    def test_dependencies_without_a_command_are_never_found(self):
        """Those are detected some other way and must not be probed on the `PATH` by mistake."""
        self.assertFalse(self.found(system.PYTHON_HEADERS, ["python3.10", "cc"]))

    def test_odoo_dependencies_name_a_package_for_every_manager_that_ships_one(self):
        for dependency in system.ODOO_SYSTEM_DEPENDENCIES:
            for manager in dependency.packages:
                self.assertIn(manager, system.PACKAGE_MANAGERS, f"{dependency.name} names an unknown {manager!r}")
