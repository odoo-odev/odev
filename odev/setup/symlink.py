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

LOCAL_BIN_PATH = Path("~/.local/bin").expanduser()
"""Directory holding the executables of the current user."""

SYSTEM_BIN_PATH = Path("/usr/local/bin")
"""Directory holding the executables of every user, used when the local one is not in `PATH`."""


# --- Values -------------------------------------------------------------------


def link_path() -> Path:
    """Return the path the `odev` command should be linked from.

    :return: The link to create, in the local binaries directory of the user when it is in `PATH`, in the
        system-wide one otherwise.
    :rtype: Path
    """
    known_env_paths = getenv("PATH", "").split(":")

    return (LOCAL_BIN_PATH if str(LOCAL_BIN_PATH) in known_env_paths else SYSTEM_BIN_PATH) / "odev"


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Set up symlinks to odev for using it as a shell command.

    :param config: Odev configuration
    """
    main_path = Path(__file__).parents[2] / "odev.sh"
    command_path = link_path()

    if not command_path.parent.exists():
        logger.debug(f"Directory {command_path.parent} does not exist, creating it")
        command_path.parent.mkdir(parents=True)

    if command_path.exists() or command_path.is_symlink():
        logger.warning(f"Symlink path {command_path} already exists, this is used to run odev as a shell command")

        if console.confirm("Would you like to overwrite it?"):
            logger.debug(f"Removing symlink path {command_path}")
            bash.execute(f"rm {command_path}", sudo=True)

    if not command_path.exists() and not command_path.is_symlink():
        logger.debug(f"Creating symlink from {command_path} to {main_path}")
        bash.execute(f"ln -s {main_path} {command_path}", sudo=True)
        logger.info("Symlink created")

    for path in (main_path, command_path):
        logger.debug(f"Checking execute permissions for {path}")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
