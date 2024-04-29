"""Shared method for debugging odev or interacting with debuggers."""

import re
from functools import lru_cache
from glob import glob
from pathlib import Path
from typing import Generator, Tuple, Union

from odev.common import string
from odev.common.logging import logging


logger = logging.getLogger(__name__)


DEBUG_MODE: bool = False
"""Whether odev is currently in debug mode."""


@lru_cache
def find_debuggers(root: Union[str, Path]) -> Generator[Tuple[Path, int], None, None]:
    """Find all call to interactive debuggers in the given directory and its subdirectories.
    :param root: The directory to search for debugger instances.
    :return: A generator of tuples containing the file path and the line number of the call to the debugger.
    """
    if isinstance(root, str):
        root = Path(root)

    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    glob_pattern = (root / "**/*.py").as_posix()

    for python_file in map(Path, glob(glob_pattern, recursive=True)):
        with python_file.open() as file:
            for position, line in enumerate(file.readlines()):
                if re.search(r"(i?pu?db)\.set_trace\(", line.split("#", 1)[0]):
                    yield python_file.resolve(), position + 1


# ------------------------------------------------------------------------------
# Find calls to interactive debuggers within odev's source code
debuggers = [f"{file.as_posix()}:{line}" for file, line in find_debuggers(Path(__file__).parents[1])]

if debuggers:
    logger.warning(f"Interactive debuggers detected:\n{string.join_bullet(debuggers)}")
    DEBUG_MODE = True
