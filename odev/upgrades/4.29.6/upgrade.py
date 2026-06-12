"""Upgrade to odev 4.29.4.

Reset the 'beta' branch of all installed plugins to their remote state.

The 'beta' branch of several plugin repositories was force-pushed. Users on the
'beta' release channel have those plugins checked out on a local 'beta' branch
whose history diverged from the rewritten remote, which would make odev's next
pull fail. This hard-resets each beta-checked-out plugin to 'origin/beta'.
"""

from git import GitCommandError

from odev.common import progress
from odev.common.connectors.git import GitConnector
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)

BETA_BRANCH = "beta"


def run(odev: Odev) -> None:
    for plugin in odev.plugins:
        git = GitConnector(plugin.name)
        repository = git.repository

        if repository is None:
            logger.debug(f"Plugin {plugin.name!r} is not a git repository, skipping")
            continue

        if git.branch != BETA_BRANCH:
            logger.debug(f"Plugin {plugin.name!r} is not on the {BETA_BRANCH!r} branch, skipping")
            continue

        try:
            with progress.spinner(f"Resetting {BETA_BRANCH!r} branch of plugin {plugin.name!r} to its remote state"):
                repository.git.fetch("origin", BETA_BRANCH)
                repository.git.reset("--hard", f"origin/{BETA_BRANCH}")
        except GitCommandError as error:
            logger.warning(f"Failed to reset {BETA_BRANCH!r} branch of plugin {plugin.name!r}: {error}")
            continue

        logger.info(f"Reset {BETA_BRANCH!r} branch of plugin {plugin.name!r} to its remote state")
