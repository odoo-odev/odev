#!/usr/bin/env python3
"""Release tooling shared by the release workflows of odev and its plugins.

Derives the next version number from the prefixes of the commits waiting on the pre-release branch, rewrites the
version file and renders the changelog of a release. Only relies on the standard library and on `git` so that it
can run from a bare checkout in any repository.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from enum import IntEnum
from pathlib import Path
from typing import NamedTuple


VERSION_PATTERN = re.compile(r"^(?P<prefix>__version__\s*=\s*[\"'])(?P<version>\d+\.\d+\.\d+)(?P<suffix>[\"'])", re.M)
"""Assignment of the version number, as found in `odev/_version.py` and in plugin manifests."""

PREFIX_PATTERN = re.compile(r"^\[(?P<prefix>[A-Za-z]+)\]")
"""Odoo-style prefix opening the subject of a commit, i.e. `[FIX]`."""

RELEASE_PREFIX = "REL"
"""Prefix of the commits authored by the release workflow, never accounted for in a release."""


class Level(IntEnum):
    """Part of the version number incremented by a change, ordered by importance."""

    PATCH = 1
    MINOR = 2
    MAJOR = 3


LEVEL_BY_PREFIX: dict[str, Level] = {
    "REF": Level.MAJOR,
    "FEAT": Level.MINOR,
    "ADD": Level.MINOR,
    "IMP": Level.MINOR,
}
"""Level incremented by each commit prefix, any other prefix increments the patch number."""

SECTION_BY_PREFIX: dict[str, str] = {
    "FEAT": "Features",
    "ADD": "Features",
    "IMP": "Improvements",
    "REF": "Refactoring",
    "FIX": "Fixes",
    "DOC": "Documentation",
}
"""Changelog section in which commits are listed, in order of appearance."""

FALLBACK_SECTION = "Other changes"


class Version(NamedTuple):
    """Semantic version number of odev or one of its plugins."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version: str) -> Version:
        """Parse a version number.

        Args:
            version: The version number, formatted as `<major>.<minor>.<patch>`.

        Returns:
            The parsed version.
        """
        major, minor, patch = (int(part) for part in version.strip().split("."))

        return cls(major, minor, patch)

    def bump(self, level: Level) -> Version:
        """Increment the version number, resetting the parts of lesser importance.

        Args:
            level: The part of the version number to increment.

        Returns:
            The incremented version.
        """
        match level:
            case Level.MAJOR:
                return Version(self.major + 1, 0, 0)

            case Level.MINOR:
                return Version(self.major, self.minor + 1, 0)

            case _:
                return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def git(*arguments: str) -> str:
    """Run a git command in the current repository.

    Args:
        *arguments: The arguments passed to git.

    Returns:
        The output of the command, stripped.
    """
    return subprocess.run(["git", *arguments], check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603, S607


def commit_prefix(subject: str) -> str:
    """Extract the prefix of a commit.

    Args:
        subject: The first line of the commit message.

    Returns:
        The uppercase prefix without its brackets, empty if the subject does not start with a prefix.
    """
    matched = PREFIX_PATTERN.match(subject.strip())

    return matched.group("prefix").upper() if matched else ""


def released_subjects(subjects: list[str]) -> list[str]:
    """Filter out the commits of the release workflow.

    Args:
        subjects: The subjects of the commits waiting for a release.

    Returns:
        The subjects of the commits that are part of the release.
    """
    return [subject for subject in subjects if subject.strip() and commit_prefix(subject) != RELEASE_PREFIX]


def release_level(subjects: list[str]) -> Level | None:
    """Find the part of the version number to increment for a set of commits.

    Args:
        subjects: The subjects of the commits waiting for a release.

    Returns:
        The most important level among the commits, `None` if there is nothing to release.
    """
    levels = [LEVEL_BY_PREFIX.get(commit_prefix(subject), Level.PATCH) for subject in released_subjects(subjects)]

    return max(levels, default=None)


def next_version(base_version: Version, head_version: Version, subjects: list[str]) -> Version | None:
    """Compute the version of the next release.

    A version already set on the pre-release branch is kept when it is higher than the computed one, so that a
    version incremented by hand is never lowered.

    Args:
        base_version: The version of the last release.
        head_version: The version currently set on the pre-release branch.
        subjects: The subjects of the commits added since the last release.

    Returns:
        The version to release, `None` if there is nothing to release.
    """
    level = release_level(subjects)

    if level is None:
        return head_version if head_version > base_version else None

    return max(base_version.bump(level), head_version)


def read_version(content: str) -> Version:
    """Read the version number assigned in a version file.

    Args:
        content: The content of the version file.

    Returns:
        The version found in the file.

    Raises:
        ValueError: If the file does not assign a version number.
    """
    matched = VERSION_PATTERN.search(content)

    if matched is None:
        raise ValueError("No `__version__` assignment found in the version file")

    return Version.parse(matched.group("version"))


def write_version(content: str, version: Version) -> str:
    """Replace the version number assigned in a version file.

    Args:
        content: The content of the version file.
        version: The version to assign.

    Returns:
        The updated content of the file.
    """
    read_version(content)

    return VERSION_PATTERN.sub(rf"\g<prefix>{version}\g<suffix>", content, count=1)


def changelog(subjects: list[str]) -> str:
    """Render the changelog of a release, grouping commits by nature.

    Args:
        subjects: The subjects of the commits added since the last release.

    Returns:
        The changelog as markdown.
    """
    sections: dict[str, list[str]] = {section: [] for section in [*SECTION_BY_PREFIX.values(), FALLBACK_SECTION]}

    for subject in released_subjects(subjects):
        section = SECTION_BY_PREFIX.get(commit_prefix(subject), FALLBACK_SECTION)
        description = PREFIX_PATTERN.sub("", subject.strip(), count=1).strip()
        sections[section].append(f"- {description}")

    return "\n\n".join(f"### {section}\n\n" + "\n".join(lines) for section, lines in sections.items() if lines)


def subjects_between(base: str, head: str) -> list[str]:
    """List the subjects of the commits reachable from a revision and not from another, oldest first.

    Args:
        base: The revision of the last release.
        head: The revision to release.

    Returns:
        The subjects of the commits.
    """
    return git("log", "--reverse", "--format=%s", f"{base}..{head}").splitlines()


def version_at(revision: str, version_file: str) -> Version:
    """Read the version number of a revision.

    Args:
        revision: The revision to read the version file from.
        version_file: The path to the version file, relative to the root of the repository.

    Returns:
        The version at that revision.
    """
    return read_version(git("show", f"{revision}:{version_file}"))


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        arguments: The arguments to parse, defaults to the arguments of the process.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    next_parser = commands.add_parser("next-version", help="print the version to release, nothing if up-to-date")
    changelog_parser = commands.add_parser("changelog", help="print the changelog of the release")

    for range_parser in (next_parser, changelog_parser):
        range_parser.add_argument("--base", required=True, help="revision of the last release")
        range_parser.add_argument("--head", required=True, help="revision to release")

    bump_parser = commands.add_parser("bump", help="write a version number to the version file")
    bump_parser.add_argument("--version", required=True, type=Version.parse, help="version to write")

    for file_parser in (next_parser, bump_parser):
        file_parser.add_argument("--version-file", required=True, help="path to the file assigning `__version__`")

    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run the release tooling.

    Args:
        arguments: The arguments of the command line, defaults to the arguments of the process.

    Returns:
        The exit code of the process.
    """
    options = parse_arguments(arguments)

    match options.command:
        case "next-version":
            version = next_version(
                version_at(options.base, options.version_file),
                version_at(options.head, options.version_file),
                subjects_between(options.base, options.head),
            )
            output = str(version) if version else ""

        case "changelog":
            output = changelog(subjects_between(options.base, options.head))

        case _:
            version_file = Path(options.version_file)
            version_file.write_text(write_version(version_file.read_text(), options.version))
            output = str(options.version)

    sys.stdout.write(f"{output}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
