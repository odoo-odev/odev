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

    def run(self):
        if not self.args.bypass_prompt:
            if self.args.version:
                if not self.odev.config.repositories.is_pull_needed(self.args.version):
                    next_pull = self.odev.config.repositories.next_pull_date(self.args.version)
                    days = (next_pull - datetime.today()).days + 1
                    logger.info(f"Skipping pull for {self.args.version!r}, next pull scheduled in {days} days")
                    return
            elif all(not self.odev.config.repositories.is_pull_needed(name) for name in self.grouped_worktrees):
                logger.info("All worktrees are recently pulled, skipping pull. Use --force to pull anyway.")
                return

        super().run()

    def run_hook(self, name: str, changes: list[tuple[str, int, int]]):
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

        self.odev.config.repositories.set_date(name, datetime.today())
