"""Manage git worktrees used within odev."""

from odev.common import args, progress
from odev.common.commands import GitCommand
from odev.common.connectors.git import GitConnector
from odev.common.console import TableHeader
from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class WorktreeCommand(GitCommand):
    """Manage git worktrees used within odev."""

    _name = "worktree"
    _aliases = ["wt"]

    _exclusive_arguments = [("list", "prune", "create", "remove", "checkout")]

    action_list = args.Flag(name="list", aliases=["-l", "--list"], description="List worktrees and their properties.")
    action_prune = args.Flag(
        name="prune",
        aliases=["-p", "--prune"],
        description="Prune worktrees with issues reported by git.",
    )
    action_create = args.Flag(name="create", aliases=["-C", "--create"], description="Create a new worktree.")
    action_remove = args.Flag(name="remove", aliases=["-r", "--remove"], description="Remove an existing worktree.")
    action_checkout = args.Flag(
        name="checkout",
        aliases=["-c", "--checkout"],
        description="Change the revisions used in an existing worktree.",
    )
    name = args.String(description="Name of the worktree to create, checkout or remove.", nargs="?")

    def run(self):
        """Run the command."""
        if self.args.list:
            self.list_worktrees()
        if self.args.prune:
            self.prune_worktrees()
        if self.args.create:
            self.create_worktree()
        if self.args.remove:
            self.remove_worktree()
        if self.args.checkout:
            self.checkout_worktree()

    def list_worktrees(self):
        """List worktrees and their properties."""
        headers = [
            TableHeader("Repository", min_width=20),
            TableHeader("Commit"),
            TableHeader("Branch"),
        ]

        self.print()

        with progress.spinner("Listing worktrees"):
            for name, worktrees in self.grouped_worktrees.items():
                self.table(
                    headers,
                    [
                        [
                            worktree.connector.name,
                            worktree.commit,
                            "<detached>" if worktree.detached else worktree.branch,
                        ]
                        for worktree in worktrees
                    ],
                    title=name,
                )

        self.console.clear_line()

    def prune_worktrees(self):
        """Prune worktrees."""
        with progress.spinner("Looking for prunable worktrees"):
            if not any(worktree.prunable for worktree in self.worktrees):
                logger.info("No worktrees to prune")
                return

        with progress.spinner("Pruning worktrees"):
            for repository in self.repositories:
                repository.prune_worktrees()

    def create_worktree(self):
        """Create a new worktree."""
        self.__check_name()

        if self.args.name in self.grouped_worktrees:
            raise self.error(f"Worktree with name '{self.args.name}' already exists")

        with progress.spinner(f"Creating worktree {self.args.name}"):
            for repository in self.repositories:
                revision = self.get_revision(repository)
                repository.create_worktree(f"{self.args.name}/{repository.path.name}", revision)

    def remove_worktree(self):
        """Remove a worktree."""
        self.__check_name()

        if self.args.name not in self.grouped_worktrees:
            raise self.error(f"Worktree with name '{self.args.name}' does not exist")

        with progress.spinner(f"Removing worktree {self.args.name}"):
            for repository in self.repositories:
                repository.remove_worktree(f"{self.args.name}/{repository.path.name}")

    def checkout_worktree(self):
        """Change the revisions used in an existing worktree."""
        self.__check_name()

        if self.args.name not in self.grouped_worktrees:
            raise self.error(
                f"Worktree with name '{self.args.name}' does not exist, use the create option to add a new worktree"
            )

        for repository in self.repositories:
            revision = self.get_revision(repository)
            repository.checkout_worktree(f"{self.args.name}/{repository.path.name}", revision)

        logger.info("Worktree revisions changed successfully")

    def get_revision(self, repository: GitConnector) -> str:
        """Get the revision to use for the new worktree."""
        if self.args.version:
            return str(OdooVersion(self.args.version))

        def sort_key(s):
            def version_to_float(v):
                try:
                    return -float("inf" if v == "master" else v)
                except ValueError:
                    return float("inf")

            if s.startswith("saas-"):
                return (1, version_to_float(s.split("-")[1]))
            if s.startswith("staging.saas-"):
                return (3, version_to_float(s.split("-")[1]))
            if s.startswith("staging."):
                return (2, version_to_float(s.split(".")[1]))
            if s.startswith("tmp.saas-"):
                return (5, version_to_float(s.split("-")[1]))
            if s.startswith("tmp."):
                return (4, version_to_float(s.split(".")[1]))
            return (0, version_to_float(s))

        branches = sorted(repository.list_remote_branches(), key=sort_key)
        ref = self.console.fuzzy(
            f"Select a branch to track for {repository.name!r}:",
            [("commit", "Specific commit"), *[(branch, branch) for branch in branches]],
        )

        if ref == "commit":
            ref = self.console.text("Specific commit SHA to track:")

        if not ref:
            raise self.error("No branch or commit SHA specified")

        return ref or repository.default_branch or "master"

    def __check_name(self):
        """Check if a name was properly given through CLI arguments."""
        if not self.args.name:
            raise self.error("You need to provide a name for the worktree.")
