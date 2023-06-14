"""Setup working directories for odev."""

import shutil
from pathlib import Path
from typing import Optional, Union

from odev.common.config import Config
from odev.common.console import console
from odev.common.logging import logging


logger = logging.getLogger(__name__)


# --- Helpers ------------------------------------------------------------------


def __resolve(path: Union[str, Path]) -> Path:
    """Resolve a path while expanding user tokens."""
    if isinstance(path, str):
        path = Path(path)

    return path.expanduser().resolve()


def __is_empty(path: Path) -> bool:
    """Check if a directory is empty."""
    return not path.exists() or not any(path.iterdir())


def __move(old: Path, new: Path) -> None:
    """Move a directory to a new location."""
    if old == new:
        logger.debug(f"Directory {old} did not change, skipping")
        return

    if not old.exists():
        logger.debug(f"Directory {old} does not exist, creating {new}")
        new.mkdir(parents=True, exist_ok=True)
        return

    if __is_empty(new) and new.exists():
        logger.debug(f"Directory {new} is empty, removing it")
        new.rmdir()

    logger.debug(f"Moving {old} to {new}")
    shutil.move(old.as_posix(), new.as_posix())


def __ask_dir(message: str, default: str = None, path: Optional[Path] = None) -> Optional[Path]:
    """Prompt for a directory path."""
    if path is None:
        path = __resolve(console.directory(message, default))

        if not __is_empty(path):
            logger.warning(f"Directory {path} is not empty")

            if not console.confirm("Use this directory without moving files?"):
                path = None

    return path


# --- Setup --------------------------------------------------------------------


def setup(config: Config) -> None:
    """Setup working directories for odev.
    :param config: Odev configuration
    """
    new_path: Optional[Path] = None
    old_path: Path = config.paths.repositories

    while new_path is None:
        new_path = __ask_dir("Where do you want to keep odoo repositories?", old_path.as_posix(), new_path)

    __move(old_path, new_path)

    logger.debug("Saving directories to configuration file")
    config.paths.repositories = new_path
