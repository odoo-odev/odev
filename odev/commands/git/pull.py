"""Pull changes in local worktrees."""

from typing import List, Tuple

from odev.commands.git.fetch import FetchCommand
from odev.common import progress
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PullCommand(FetchCommand):
    """Pull changes in local worktrees managed by odev."""

    _name = "pull"

    def run_hook(self, name: str, changes: List[Tuple[str, int, int]]):
        """Print a summary of the pending changes for a worktree."""
        for change in changes:
            repository, behind, _ = change
            worktree = next(
                (
                    worktree
                    for worktree in self.worktrees
                    if worktree.name == name and worktree.connector.name == repository
                ),
                None,
            )

            if worktree is None:
                raise self.error(f"Worktree {name!r} does not exist")

            if worktree.detached:
                logger.info(f"Worktree {name!r} is detached")
                continue

            if not behind:
                logger.info(
                    f"No pending changes for worktree {name!r} in {repository!r} for version {worktree.branch!r}"
                )
                continue

            with progress.spinner(
                f"Pulling {behind} commits in {worktree.connector.name!r} for version {worktree.branch!r}"
            ):
                worktree.connector.pull_worktrees([worktree], force=True)
                logger.info(f"Pulled {behind} commits in {worktree.connector.name!r} for version {worktree.branch!r}")
