"""Self update Odev by pulling latest changes from the git repository."""

import sys
from pathlib import Path
from git import Repo, Remote

from odev.common.config import ConfigManager


ODEV_PATH: Path = Path(__file__).parents[2]
"""Local path to the odev repository."""


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

    remote = repo.remotes[remote_branch.remote_name]
    rev_list = repo.git.rev_list('--left-right', '--count', f'{remote.name}...HEAD')
    diff = repo.git.diff("--name-only")
    import ipdb; ipdb.set_trace()



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
    is_behind = __git_branch_behind(odev_repo)
    # try:
    #     did_update = git_pull(
    #         ODEV_PATH,
    #         "odev",
    #         verbose=False,
    #         confirm_message_t=("An update is available for odev, do you want to download it now?"),
    #     )
    # except (MissingTrackingBranch, HeadRefMismatch) as exc:
    #     _logger.debug(f"{exc}, odev running in development mode")
    #     return False

    # if did_update:
    #     _logger.info("Checking for new odev package requirements")
    #     install_packages(requirements_dir=ODEV_PATH)

    # return did_update


# def self_update() -> bool:
#     """
#     Check for updates in the odev repository and download them if necessary.

#     :return: True if updates were pulled, False otherwise
#     """
#     if not sys.stdout.isatty() or not sys.stdin.isatty():
#         return False

#     config = ConfigManager("odev")
#     odev_path = config.get("paths", "odev")

#     default_date = (datetime.today() - timedelta(days=1)).strftime(DEFAULT_DATETIME_FORMAT)
#     update_check_interval = config.get("update", "check_interval") or 1
#     last_update_check = config.get("update", "last_check") or default_date
#     last_check_diff = (datetime.today() - datetime.strptime(last_update_check, DEFAULT_DATETIME_FORMAT)).days

#     if last_check_diff < update_check_interval:
#         return False

#     try:
#         did_update: bool = git_pull(
#             odev_path,
#             "odev",
#             verbose=False,
#             confirm_message_t=("An update is available for odev, do you want to download it now?"),
#         )
#     except (MissingTrackingBranch, HeadRefMismatch) as exc:
#         _logger.debug(f"{exc}, odev running in development mode")
#         return False

#     if did_update:
#         _logger.info("Checking for new odev package requirements")
#         install_packages(requirements_dir=odev_path)

#     config.set("update", "last_check", datetime.today().strftime(DEFAULT_DATETIME_FORMAT))

#     return did_update
