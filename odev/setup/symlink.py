"""Setup symlinks to odev for using it as a shell command."""

import stat
from os import getenv
from pathlib import Path

from odev.common import bash
from odev.common.console import console
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


PRIORITY = 10


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Set up symlinks to odev for using it as a shell command.

    :param config: Odev configuration
    """
    main_path = Path(__file__).parents[2] / "main.py"
    known_env_paths = getenv("PATH", "").split(":")
    local_path = Path("~/.local/bin").expanduser()
    link_path = (local_path if str(local_path) in known_env_paths else Path("/usr/local/bin")) / "odev"

    if not link_path.parent.exists():
        logger.debug(f"Directory {link_path.parent} does not exist, creating it")
        link_path.parent.mkdir(parents=True)

    if link_path.exists() or link_path.is_symlink():
        logger.warning(f"Symlink path {link_path} already exists, this is used to run odev as a shell command")

        if console.confirm("Would you like to overwrite it?"):
            logger.debug(f"Removing symlink path {link_path}")
            bash.execute(f"rm {link_path}", sudo=True)

    if not link_path.exists() and not link_path.is_symlink():
        logger.debug(f"Creating symlink from {link_path} to {main_path}")
        bash.execute(f"ln -s {main_path} {link_path}", sudo=True)
        logger.info("Symlink created")

    for path in (main_path, link_path):
        logger.debug(f"Checking execute permissions for {path}")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
