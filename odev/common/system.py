"""Description of the operating system odev runs on and of the packages it can install."""

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from odev.common import string


__all__ = [
    "ODOO_SYSTEM_DEPENDENCIES",
    "SystemDependency",
    "install_instructions",
    "package_manager",
]


PACKAGE_MANAGERS: Mapping[str, str] = {
    "apt-get": "sudo apt-get install -y {packages}",
    "dnf": "sudo dnf install -y {packages}",
    "zypper": "sudo zypper install -y {packages}",
    "pacman": "sudo pacman -S --needed {packages}",
    "apk": "sudo apk add {packages}",
    "brew": "brew install {packages}",
}
"""Command installing packages with each of the package managers odev knows about, keyed by the
executable to look for on the `PATH`. Package managers shipped by the distribution come first so
that a Linux machine on which Homebrew is also installed is told to use its own.
"""


@dataclass(frozen=True)
class SystemDependency:
    """A part of the operating system Odoo needs to build its python dependencies from source."""

    name: str
    """Human-readable description, displayed as-is when no package can be named for the current
    system. May contain placeholders, `{version}` being the version of python being installed.
    """

    packages: Mapping[str, str] = field(default_factory=dict)
    """Package providing this dependency, per package manager. A package manager absent from this
    mapping has nothing to install: Arch Linux ships the python headers within `python` itself and
    the compiler of macOS comes from `xcode-select --install`, not from Homebrew.
    """

    commands: Sequence[str] = ()
    """Executables proving, if any of them is found on the `PATH`, that this dependency is
    installed. Dependencies detected some other way leave this empty and are never found.
    """

    @property
    def found(self) -> bool:
        """Whether the dependency can be proven to be installed on the current system."""
        return any(shutil.which(command) for command in self.commands)

    def package(self, manager: str, **placeholders: str) -> str | None:
        """Package to install to provide this dependency with a given package manager.

        :param manager: The package manager to install the dependency with.
        :param placeholders: Values for the placeholders in the name of the package.
        :return: The name of the package, or None if the package manager does not ship one.
        :rtype: Optional[str]
        """
        package = self.packages.get(manager)
        return package.format(**placeholders) if package is not None else None


PYTHON_INTERPRETER = SystemDependency(
    name="the python {version} interpreter",
    packages={
        "apt-get": "python{version}",
        "dnf": "python{version}",
        "zypper": "python{version}",
        "pacman": "python",
        "apk": "python3",
        "brew": "python@{version}",
    },
)

PYTHON_HEADERS = SystemDependency(
    name="the development headers of python {version} (Python.h)",
    packages={
        "apt-get": "python{version}-dev",
        "dnf": "python{version}-devel",
        "zypper": "python{version}-devel",
        "apk": "python3-dev",
    },
)

C_COMPILER = SystemDependency(
    name="a C compiler",
    packages={
        "apt-get": "build-essential",
        "dnf": "gcc",
        "zypper": "gcc",
        "pacman": "base-devel",
        "apk": "build-base",
    },
    commands=("cc", "gcc", "clang"),
)

POSTGRESQL_HEADERS = SystemDependency(
    name="the PostgreSQL client headers (pg_config)",
    packages={
        "apt-get": "libpq-dev",
        "dnf": "libpq-devel",
        "zypper": "postgresql-devel",
        "pacman": "postgresql-libs",
        "apk": "postgresql-dev",
        "brew": "libpq",
    },
    commands=("pg_config",),
)

LDAP_HEADERS = SystemDependency(
    name="the OpenLDAP and SASL headers",
    packages={
        "apt-get": "libldap2-dev libsasl2-dev",
        "dnf": "openldap-devel",
        "zypper": "openldap2-devel cyrus-sasl-devel",
        "pacman": "libldap libsasl",
        "apk": "openldap-dev",
        "brew": "openldap",
    },
)

ODOO_SYSTEM_DEPENDENCIES: Sequence[SystemDependency] = (
    PYTHON_INTERPRETER,
    PYTHON_HEADERS,
    C_COMPILER,
    POSTGRESQL_HEADERS,
    LDAP_HEADERS,
)
"""Everything Odoo needs to build its python dependencies from source, in the order in which it is
worth installing it.
"""


def package_manager() -> str | None:
    """Find the package manager of the current system.

    :return: The name of the package manager, or None if odev does not know the one in use.
    :rtype: Optional[str]
    """
    return next((manager for manager in PACKAGE_MANAGERS if shutil.which(manager)), None)


def install_instructions(dependencies: Sequence[SystemDependency], **placeholders: str) -> str:
    """Describe what is missing from the current system and how to install it.

    Odev runs on systems it does not control, and cannot name a package for all of them, so the
    dependencies are always described in plain words; the command is only added on top when the
    package manager in use is one odev knows.

    :param dependencies: The dependencies missing from the current system.
    :param placeholders: Values for the placeholders in the names of the dependencies and of their
        packages, `version` being the version of python being installed.
    :return: A bullet list of the missing dependencies, followed by the command installing them.
    :rtype: str
    """
    instructions = string.join_bullet([dependency.name.format(**placeholders) for dependency in dependencies])
    manager = package_manager()

    if manager is None:
        return instructions

    packages = [package for dependency in dependencies if (package := dependency.package(manager, **placeholders))]

    if not packages:
        return instructions

    command = PACKAGE_MANAGERS[manager].format(packages=" ".join(packages))
    return f"{instructions}\n\nInstall them by running:\n{string.stylize(command, 'color.cyan')}"
