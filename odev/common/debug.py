"""Shared method for debugging odev or interacting with debuggers."""

import subprocess
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from odev.common import bash, string
from odev.common.config import CONFIG_DIR
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DEBUG_MODE: bool = False
"""Whether odev is currently in debug mode."""


@lru_cache
def find_debuggers(root: str | Path, *, follow_symlinks: bool = True) -> Generator[tuple[Path, int], None, None]:
    """Find all call to interactive debuggers in the given directory and its subdirectories.
    :param root: The directory to search for debugger instances.
    :param follow_symlinks: Whether to descend into symlinked directories found under the root.
    :return: A generator of tuples containing the file path and the line number of the call to the debugger.
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

    for line in output.splitlines():
        file, position, _ = line.split(":", 2)
        yield Path(file), int(position)


# ------------------------------------------------------------------------------
# Find calls to interactive debuggers within odev's source code.
# The repository may contain an `odev/plugins` symlink used for IDE import resolution: do not follow symlinks when
# scanning the package, the installed plugins are scanned separately from their canonical location.
sources: list[tuple[Path, bool]] = [(Path(__file__).parents[1], False)]
plugins_path = CONFIG_DIR / "plugins"

if plugins_path.is_dir():
    sources.append((plugins_path, True))

debuggers = [
    f"{file.as_posix()}:{line}"
    for source, follow_symlinks in sources
    for file, line in find_debuggers(source, follow_symlinks=follow_symlinks)
]

if debuggers:
    logger.warning(f"Interactive debuggers detected:\n{string.join_bullet(debuggers)}")
    DEBUG_MODE = True
