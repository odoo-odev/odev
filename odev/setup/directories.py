"""Setup working directories for odev."""

import shutil
from pathlib import Path

from odev.common.console import console
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


PRIORITY = 20


# --- Helpers ------------------------------------------------------------------


def __resolve(path: str | Path) -> Path:
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
        logger.debug(f"Directory {old} does not exist, creating {new} as en empty directory")
        new.mkdir(parents=True, exist_ok=True)
        return

    if __is_empty(new) and new.exists():
        logger.debug(f"Directory {new} exists but is empty, removing it")
        new.rmdir()

    logger.debug(f"Moving {old} to {new}")
    shutil.move(old.as_posix(), new.as_posix())


def __ask_dir(message: str, default: str | None = None, path: Path | None = None) -> Path | None:
    """Prompt for a directory path."""
    if path is None:
        asked_path = console.directory(message, default)

        if asked_path is not None:
            path = __resolve(asked_path)

            if not __is_empty(path):
                logger.warning(f"Directory {path} is not empty")

                if not console.confirm("Use this directory without moving existing files?"):
                    path = None

    return path


def __get_dir(message: str, default: Path) -> Path | None:
    """Prompt for a directory path."""
    new_path: Path | None = None

    while new_path is None:
        new_path = __ask_dir(message, default.as_posix(), new_path)

    __move(default, new_path)
    return new_path


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Set up working directories for odev.

    :param config: Odev configuration
    """
    logger.info(
        """
        Odev manages a few directories on your system. You can change their location to your liking.
        These directories include:
        - Odoo and project repositories, stored under /chosen/path/organization/repository
        - Dump files, which are downloaded when using the dump command to restore a database
        """
    )

    odev.config.paths.repositories = __get_dir(
        "Where do you want to store repositories?",
        odev.config.paths.repositories,
    )
    odev.config.paths.dumps = __get_dir(
        "Where do you want to store dump files?",
        odev.config.paths.dumps,
    )
