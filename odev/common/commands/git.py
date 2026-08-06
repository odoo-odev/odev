from abc import ABC
from collections.abc import Generator

from odev.common import args
from odev.common.commands import Command
from odev.common.connectors import GitConnector, GitWorktree
from odev.common.logging import logging
from odev.common.odoobin import odoo_repositories


logger = logging.getLogger(__name__)


class GitCommand(Command, ABC):
    """Base command class for interacting with git repositories and worktrees."""

    version = args.String(aliases=["-V", "--version"], description="Act on a specific Odoo version only.")

    @property
    def repositories(self) -> Generator[GitConnector, None, None]:
        """Iterate over Odoo repositories."""
        return odoo_repositories()

    @property
    def worktrees(self) -> Generator[GitWorktree, None, None]:
        """Iterate over worktrees in Odoo repositories."""
        for repository in self.repositories:
            for worktree in repository.worktrees():
                if not worktree.path.exists():
                    logger.debug(f"Skipping missing worktree {worktree.name!r} at {worktree.path!s}")
                    continue
                if getattr(getattr(self, "args", None), "version", None) and worktree.name != self.args.version:
                    continue
                yield worktree

    @property
    def grouped_worktrees(self) -> dict[str, list[GitWorktree]]:
        """Group worktrees by name."""
        worktrees: dict[str, list[GitWorktree]] = {}
        for worktree in self.worktrees:
            worktrees.setdefault(worktree.name, []).append(worktree)
        return worktrees
