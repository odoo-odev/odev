from abc import ABC
from typing import Dict, Generator, List

from odev.common import args
from odev.common.commands import Command
from odev.common.connectors import GitConnector, GitWorktree
from odev.common.odoobin import odoo_repositories
from odev.common.version import OdooVersion


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
                if not worktree.detached and (
                    not self.args.version or OdooVersion(worktree.branch) == OdooVersion(self.args.version)
                ):
                    yield worktree

    @property
    def grouped_worktrees(self) -> Dict[str, List[GitWorktree]]:
        """Group worktrees by name."""
        worktrees: Dict[str, List[GitWorktree]] = {}
        for worktree in self.worktrees:
            worktrees.setdefault(worktree.name, []).append(worktree)
        return worktrees
