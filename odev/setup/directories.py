"""Setup working directories for odev."""

import shutil
from pathlib import Path
from typing import Optional, Union

from odev.common import prompt
from odev.common.logging import logging
from odev.common.config import ConfigManager


logger = logging.getLogger(__name__)


# --- Helpers ------------------------------------------------------------------


def __resolve(path: Union[str, Path]) -> Path:
    """Resolve a path while expanding user tokens."""
    if isinstance(path, str):
        path = Path(path)

    return path.expanduser().resolve()


def __is_empty(path: Path) -> bool:
    """Check if a directory is empty."""
    return path.exists() and not any(path.iterdir())


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
    shutil.move(str(old), str(new))


def __ask_dir(message: str, default: str = None, path: Optional[Path] = None) -> Optional[Path]:
    """Prompt for a directory path."""
    if path is None:
        path = __resolve(prompt.directory(message, default))

        if not __is_empty(path):
            logger.warning(f"Directory {path} is not empty and cannot be overridden")

            if not prompt.confirm("Use this directory without moving files?"):
                path = None

    return path


# --- Setup --------------------------------------------------------------------


def setup(config: Optional[ConfigManager] = None) -> None:
    """Setup working directories for odev.

    :param config: Configuration manager
    """
    standard: Optional[Path] = None
    custom: Optional[Path] = None

    config_section, config_option_standard, config_option_custom = "paths", "odoo", "dev"

    old_standard: str = __resolve(config.get(config_section, config_option_standard, "~/odoo/versions"))
    old_custom: str = __resolve(config.get(config_section, config_option_custom, "~/odoo/dev"))

    while standard is None or custom is None:
        standard = __ask_dir(
            "Where do you want to keep odoo standard repositories?",
            str(old_standard),
            standard,
        )

        custom = __ask_dir(
            "Where do you want to keep odoo-ps repositories?",
            str(old_custom),
            custom,
        )

        if standard == custom:
            logger.error("Standard and custom directories must be different")
            standard = custom = None

    __move(old_standard, standard)
    __move(old_custom, custom)

    logger.debug("Saving directories to configuration file")
    config.set(config_section, config_option_standard, str(standard))
    config.set(config_section, config_option_custom, str(custom))
