"""Pull changes in local worktrees."""

from odev.common import progress
from odev.common.commands import GitCommand
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PullCommand(GitCommand):
    """Pull changes in local worktrees managed by odev."""

    _name = "pull"

    def run(self):
        for worktree in self.worktrees:
            worktree.repository.remotes.origin.fetch()
            behind, _ = worktree.pending_changes()

            if not behind:
                continue

            with progress.spinner(
                f"Pulling {behind} commits in {worktree.connector.name!r} for version {worktree.branch!r}"
            ):
                worktree.connector.pull_worktrees([worktree], force=True)
                logger.info(f"Pulled {behind} commits in {worktree.connector.name!r} for version {worktree.branch!r}")

        logger.info("Worktrees are up-to-date")
