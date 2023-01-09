"""Setup symlinks to odev for using it as a shell command."""

import stat
from pathlib import Path
from typing import Optional

from odev.common import prompt
from odev.common.logging import logging
from odev.common.config import ConfigManager


logger = logging.getLogger(__name__)


# --- Setup --------------------------------------------------------------------


def setup(config: Optional[ConfigManager] = None) -> None:
    """Setup symlinks to odev for using it as a shell command."""
    main_path = Path(__file__).parents[2] / "main.py"
    link_path = Path("~/.local/bin/odev").expanduser()

    if not link_path.parent.exists():
        logger.debug(f"Directory {link_path.parent} does not exist, creating it")
        link_path.parent.mkdir(parents=True)

    if link_path.exists():
        logger.warning(f"Symlink path {link_path} already exists")

        if prompt.confirm(f"Would you like to overwrite it?"):
            logger.debug(f"Removing symlink path {link_path}")
            link_path.unlink(missing_ok=True)

    if not link_path.exists():
        logger.debug(f"Creating symlink from {link_path} to {main_path}")
        link_path.symlink_to(main_path)

    for path in (main_path, link_path):
        logger.debug(f"Checking execute permissions for {path}")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
