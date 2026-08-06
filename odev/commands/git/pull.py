"""Pull changes in local worktrees."""

from datetime import datetime

from odev.commands.git.fetch import FetchCommand
from odev.common import progress
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class PullCommand(FetchCommand):
    """Pull changes in local worktrees managed by odev."""

    _name = "pull"
    _help = "Pull changes in local worktrees managed by odev."

    def run_hook(self, name: str, changes: list[tuple[str, int, int]]):
        """Pull the pending changes for a worktree and print a summary of the operation."""
        self.console.title_rule(name)

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
                logger.info(f"Detached worktree in {repository!r}")
                continue

            if not behind:
                logger.info(f"No pending changes in {repository!r} for version {worktree.branch!r}")
                continue

            with progress.spinner(f"Pulling {behind} commits in {repository!r} for version {worktree.branch!r}"):
                worktree.connector.pull_worktrees([worktree], force=True)
                logger.info(f"Pulled {behind} commits in {repository!r} for version {worktree.branch!r}")

        self.print()
        self.odev.config.repositories.set_date(name, datetime.today())
