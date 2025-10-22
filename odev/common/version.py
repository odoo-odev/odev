"""Utilities for versioning."""

import collections
import itertools
import re

from packaging.version import InvalidVersion, _BaseVersion


__all__ = ["OdooVersion"]


_Version = collections.namedtuple("_Version", ["major", "minor", "module", "saas", "master", "edition"])

MIN_VERSION_LENGTH = 3
ODOO_VERSION_PATTERN = r"""
    (?:
        (?P<master>master)?             # master
        |
        (?P<saas>saas[-~])?             # saas
        (?P<major>(?:[0-9]+)?)          # odoo major version
        [\.]?
        (?P<minor>(?:[0-9]+)?)          # odoo minor version
        [\.]?
        (?P<module>(?:[0-9]+\.?)*)?     # module version
        (?P<edition>\+[a-z])?           # edition
    )
"""


class OdooVersion(_BaseVersion):
    """Version parser adapted for Odoo."""

    _regex = re.compile(r"^\s*" + ODOO_VERSION_PATTERN + r"\s*$", re.VERBOSE | re.IGNORECASE)
    """Regex to parse the version string."""

    _version: _Version
    """Parsed out version."""

    def __init__(self, version: str):
        """Validate the version and parse it into pieces."""
        match = self._regex.search(version)

        if not match:
            raise InvalidVersion(f"Invalid version: '{version}'")

        module_version = tuple(int(i) for i in match.group("module").split(".")) if match.group("module") else ()

        while len(module_version) < MIN_VERSION_LENGTH:
            module_version += (0,)

        # Store the parsed out pieces of the version
        self._version = _Version(
            major=int(match.group("major")) if match.group("major") else 0,
            minor=int(match.group("minor")) if match.group("minor") else 0,
            module=module_version,
            saas=match.group("saas") is not None,
            master=match.group("master") is not None,
            edition=match.group("edition"),
        )

        # Generate a key which will be used for sorting
        self._key = _cmpkey(
            self._version.master,
            self._version.major,
            self._version.minor,
            self._version.module,
            self._version.edition,
            self._version.saas,
        )

    def __str__(self) -> str:
        """Return the string representation of the version."""
        if self.master:
            return "master"

        version = f"{self.major}.{self.minor}"

        if self.saas:
            version = f"saas-{version}"

        return version

    def __repr__(self) -> str:
        return f"OdooVersion({self!s})"

    def __bool__(self) -> bool:
        """Return True if the version is not empty."""
        return bool(self.major or self.minor or self.module or self.master)

    @property
    def major(self) -> int:
        """Get the major version."""
        return self._version.major

    @property
    def minor(self) -> int:
        """Get the minor version."""
        return self._version.minor

    @property
    def module(self) -> tuple:
        """Get the module version."""
        return self._version.module

    @property
    def saas(self) -> bool:
        """Get whether the version is for SaaS."""
        return self._version.saas

    @property
    def master(self) -> bool:
        """Get whether this is the master version."""
        return self._version.master

    @property
    def edition(self) -> str | None:
        """Get the edition."""
        return self._version.edition


def _cmpkey(master: bool, major: int, minor: int, module: tuple, edition: str | None, saas: bool):  # noqa: PLR0913
    # When we compare a release version, we want to compare it with all of the
    # trailing zeros removed. So we'll use a reverse the list, drop all the now
    # leading zeros until we come to something non zero, then take the rest
    # re-reverse it back into the correct order and make it a tuple and use
    # that for our sorting key.
    _module = tuple(reversed(list(itertools.dropwhile(lambda x: x == 0, reversed(module)))))

    # Saas versions should sort after non-saas versions
    _saas = int(saas)

    # Master versions should sort before non-master versions
    _master = int(master)

    return _master, major, minor, _module, edition, _saas
