"""Utilities for versioning."""

import collections
import itertools
import re

from packaging.version import InvalidVersion, _BaseVersion


_Version = collections.namedtuple("_Version", ["major", "minor", "module", "saas"])


ODOO_VERSION_PATTERN = r"""
    (?:
        (?P<saas>saas-)?                # saas
        (?P<major>(?:[0-9]+)?)          # odoo major version
        [\.]?
        (?P<minor>(?:[0-9]+)?)          # odoo minor version
        [\.]?
        (?P<module>(?:[0-9]+\.?)*)?     # module version
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

        # Store the parsed out pieces of the version
        self._version = _Version(
            major=int(match.group("major")) if match.group("major") else 0,
            minor=int(match.group("minor")) if match.group("minor") else 0,
            module=tuple(int(i) for i in match.group("module").split(".")) if match.group("module") else (),
            saas=match.group("saas") is not None,
        )

        # Generate a key which will be used for sorting
        self._key = _cmpkey(
            self._version.major,
            self._version.minor,
            self._version.module,
            self._version.saas,
        )

    def __str__(self) -> str:
        """Return the string representation of the version."""
        version = f"{self.major}.{self.minor}"

        if self.saas:
            version = f"saas-{version}"

        return version

    def __repr__(self) -> str:
        return f"<OdooVersion({str(self)})>"

    def __bool__(self) -> bool:
        """Return True if the version is not empty."""
        return bool(self.major or self.minor or self.module)

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
        """Get the saas version."""
        return self._version.saas


def _cmpkey(major: int, minor: int, module: tuple, saas: bool):
    # When we compare a release version, we want to compare it with all of the
    # trailing zeros removed. So we'll use a reverse the list, drop all the now
    # leading zeros until we come to something non zero, then take the rest
    # re-reverse it back into the correct order and make it a tuple and use
    # that for our sorting key.
    _module = tuple(reversed(list(itertools.dropwhile(lambda x: x == 0, reversed(module)))))

    # Saas versions should sort after non-saas versions
    _saas = int(saas)

    return major, minor, _module, _saas