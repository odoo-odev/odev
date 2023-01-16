"""Self update Odev by pulling latest changes from the git repository."""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from git import Repo, Remote

from odev.common.config import ConfigManager
from odev.common.logging import logging
from odev.common.python import PythonEnv
from odev.common import bash
from odev.common import prompt

from odev.constants import DEFAULT_DATETIME_FORMAT

logger = logging.getLogger(__name__)


ODEV_PATH: Path = Path(__file__).parents[2]
"""Local path to the odev repository."""


# --- Helpers ------------------------------------------------------------------


def __git_branch_behind(repo: Repo) -> bool:
    """Assess whether the current branch is behind the remote tracking branch.

    :param repo: Git repository
    :param branch: Branch to check
    :return: Whether the branch is behind the remote tracking branch
    :rtype: bool
    """
    remote_branch = repo.active_branch.tracking_branch()

    if remote_branch is None:
        return False

    remote: Remote = repo.remotes[remote_branch.remote_name]
    rev_list: str = repo.git.rev_list('--left-right', '--count', f'{remote.name}...HEAD')
    commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split('\t')]
    message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
    message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"

    if commits_behind and commits_ahead:
        logger.debug(f"Odev is {message_behind} and {message_ahead} {remote.name}")
    elif commits_behind:
        logger.debug(f"Odev is {message_behind} {remote.name}")
    elif commits_ahead:
        logger.debug(f"Odev is {message_ahead} {remote.name}")
    else:
        logger.debug(f"Odev is up-to-date with {remote.name}")

    if commits_ahead:
        logger.debug("Running in development mode (no self-update)")
        return False

    return bool(commits_behind)


def __requirements_changed(repo: Repo) -> bool:
    """Assess whether the requirements.txt file was modified.

    :param repo: Git repository
    :return: Whether the requirements.txt file has changed
    :rtype: bool
    """
    requirements_file = ODEV_PATH / "requirements.txt"
    requirements_changed = repo.git.diff("--name-only", "HEAD", requirements_file).strip() == str(requirements_file)

    if requirements_changed:
        logger.debug("Odev requirements have changed since last version")

    return requirements_changed


def __date_check_interval(config: ConfigManager) -> bool:
    """Check whether the last check date is older than today minus the check interval.

    :param config: Odev configuration
    :return: Whether the last check date is older than today minus the check interval
    :rtype: bool
    """
    default_date = (datetime.today() - timedelta(days=1)).strftime(DEFAULT_DATETIME_FORMAT)
    check_date = config.get("update", "date", default_date)
    check_interval = config.get("update", "interval", 1)
    check_diff = (datetime.today() - datetime.strptime(check_date, DEFAULT_DATETIME_FORMAT)).days

    return check_diff >= check_interval


def __update_prompt(config: ConfigManager) -> bool:
    """Prompt the user to update odev if a new version is available.

    :param config: Odev configuration
    :return: Whether the user wants to update odev
    :rtype: bool
    """
    update_mode = config.get("update", "mode", "ask")
    assert update_mode in ("ask", "always", "never")

    if update_mode == "ask":
        return prompt.confirm("An update is available for odev, do you want to download it now?")

    return update_mode == "always"


# --- Methods ------------------------------------------------------------------

def update(config: ConfigManager) -> bool:
    """
    Check for updates in the odev repository and download them if necessary.

    :param config: Odev configuration
    :return: Whether updates were pulled and installed
    :rtype: bool
    """
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        return False

    odev_repo = Repo(ODEV_PATH)

    if not __date_check_interval(config) or not __git_branch_behind(odev_repo):
        bash.detached(f"cd {odev_repo.working_dir} && git fetch")
        return False

    if not __update_prompt(config):
        return False

    logger.debug(f"Pulling latest changes from odev repository on branch {odev_repo.active_branch.tracking_branch()}")
    config.set("update", "date", datetime.now().strftime(DEFAULT_DATETIME_FORMAT))
    install_requirements = __requirements_changed(odev_repo)
    odev_repo.remotes.origin.pull()

    if install_requirements:
        logger.debug("Installing new odev package requirements")
        PythonEnv().install_requirements(ODEV_PATH)

    return True


def restart() -> None:
    """Restart the current process with the latest version of odev."""
    logger.debug("Restarting odev")
    os.execv(sys.argv[0], sys.argv)
