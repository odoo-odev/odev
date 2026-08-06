"""Shared method for debugging odev or interacting with debuggers."""

import json
import os
import subprocess
from pathlib import Path

from odev.common import bash
from odev.common.config import CONFIG_DIR
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DEBUG_CACHE_PATH: Path = CONFIG_DIR / "debuggers.json"
"""Path to the file caching the result of the last scan for interactive debuggers."""


_debuggers: list[str] | None = None
"""Calls to interactive debuggers found in odev's sources, resolved on first access."""


def find_debuggers(root: str | Path, *, follow_symlinks: bool = True) -> list[tuple[Path, int]]:
    """Find all call to interactive debuggers in the given directory and its subdirectories.
    :param root: The directory to search for debugger instances.
    :param follow_symlinks: Whether to descend into symlinked directories found under the root.
    :return: A list of tuples containing the file path and the line number of the call to the debugger.
    """
    if isinstance(root, str):
        root = Path(root)

    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    recursive = "R" if follow_symlinks else "r"

    try:
        grep = bash.execute(
            rf"""grep -{recursive}nE "^[[:space:]]*[^#]*((i?pu?db)\.set_trace\(|pu\.db|breakpoint\(\))" {root.as_posix()} --include='*.py'"""
        )
        output = grep.stdout.decode() if grep is not None else ""
    except subprocess.CalledProcessError:
        output = ""

    found: list[tuple[Path, int]] = []

    for line in output.splitlines():
        file, position, _ = line.split(":", 2)
        found.append((Path(file), int(position)))

    return found


def debuggers() -> list[str]:
    """List the calls to interactive debuggers found in odev's sources and its plugins.

    :return: The locations of the calls, formatted as `path:line`.
    """
    global _debuggers  # noqa: PLW0603

    if _debuggers is None:
        _debuggers = _resolve_debuggers()

    return _debuggers


def debug_mode() -> bool:
    """Whether odev's sources contain a call to an interactive debugger.

    A live display and an interactive debugger cannot share the terminal, so odev degrades spinners and progress
    bars to plain log messages as soon as one is found.
    """
    return bool(debuggers())


def _sources() -> list[tuple[Path, bool]]:
    """List the directories to scan, and whether symlinks must be followed within them.

    The repository may contain an `odev/plugins` symlink used for IDE import resolution: do not follow symlinks when
    scanning the package, the installed plugins are scanned separately from their canonical location.
    """
    sources: list[tuple[Path, bool]] = [(Path(__file__).parents[1], False)]
    plugins_path = CONFIG_DIR / "plugins"

    if plugins_path.is_dir():
        sources.append((plugins_path, True))

    return sources


def _fingerprint(sources: list[tuple[Path, bool]]) -> list[float]:
    """Compute a cheap signature of the sources, used to detect changes since the last scan.

    Walking the trees for their modification times costs a fraction of what grepping through their content does, so
    the actual scan only runs again once a Python file was added, removed or modified.

    :param sources: The directories to scan, and whether symlinks must be followed within them.
    :return: The number of Python files found, and the most recent modification time among them.
    """
    count: int = 0
    newest: float = 0.0

    for root, follow_symlinks in sources:
        for directory, _, filenames in os.walk(root, followlinks=follow_symlinks):
            for filename in filenames:
                if filename.endswith(".py"):
                    count += 1
                    newest = max(newest, os.stat(Path(directory, filename)).st_mtime)

    return [count, newest]


def _resolve_debuggers() -> list[str]:
    """Scan the sources for calls to interactive debuggers, reusing the cached result when they did not change."""
    sources = _sources()
    fingerprint = _fingerprint(sources)
    cached = _read_cache()

    if cached is not None and cached.get("fingerprint") == fingerprint:
        return cached["debuggers"]

    found = [
        f"{file.as_posix()}:{line}"
        for source, follow_symlinks in sources
        for file, line in find_debuggers(source, follow_symlinks=follow_symlinks)
    ]

    _write_cache(fingerprint, found)

    return found


def _read_cache() -> dict | None:
    """Read the result of the last scan, or None if it is missing or unusable."""
    try:
        with DEBUG_CACHE_PATH.open(encoding="utf-8") as cache:
            return json.load(cache)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(fingerprint: list[float], found: list[str]) -> None:
    """Save the result of a scan so that the next runs can reuse it.

    :param fingerprint: Signature of the sources that were scanned.
    :param found: The locations of the calls to interactive debuggers that were found.
    """
    try:
        DEBUG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with DEBUG_CACHE_PATH.open("w", encoding="utf-8") as cache:
            json.dump({"fingerprint": fingerprint, "debuggers": found}, cache)
    except OSError as error:
        logger.debug(f"Failed to cache the scan for interactive debuggers: {error}")
