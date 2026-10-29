"""List the git repositories cloned locally."""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from odev.common import args, progress, string
from odev.common.commands import Command
from odev.common.console import TableHeader
from odev.common.logging import logging
from odev.common.mixins import ListLocalDatabasesMixin


logger = logging.getLogger(__name__)


@dataclass
class ClonedRepository:
    """Git status of a repository cloned locally."""

    name: str
    """The name of the repository, its path relative to the repositories directory: `organization/repository`
    on GitHub, `host/group/.../repository` on other hosts.
    """

    path: Path
    """The local path of the repository."""

    branch: str = ""
    """The checked out branch, or a marker followed by the short hash of the commit if the head is detached."""

    changes: int = 0
    """The number of entries reported by `git status`, an untracked directory counting as one entry."""

    ahead: int | None = None
    """The number of local commits not pushed to the tracking branch, None without a tracking branch."""

    behind: int | None = None
    """The number of commits of the tracking branch not pulled locally, None without a tracking branch."""

    last_commit: datetime | None = None
    """The date of the last commit of the checked out revision."""

    databases: list[str] = field(default_factory=list)
    """The local databases linked to the repository."""


ORDER_MAPPING: dict[str, Callable[[ClonedRepository], Any]] = {
    "name": lambda repository: repository.name.lower(),
    "date": lambda repository: (repository.last_commit is not None, repository.last_commit),
    "changes": lambda repository: repository.changes,
    "databases": lambda repository: len(repository.databases),
}


class RepositoriesCommand(ListLocalDatabasesMixin, Command):
    """List the git repositories cloned under the path managed by odev, with their checked out branch,
    uncommitted changes, commits ahead and behind their tracking branch as of the last fetch
    and the local databases linked to them.
    """

    _name = "repositories"
    _aliases = ["repos"]

    names_only = args.Flag(
        aliases=["-1", "--names-only"],
        description="List repository names one per line - useful for parsing.",
    )
    expression = args.Regex(
        aliases=["-e", "--expression"],
        description="Regular expression pattern to filter listed repositories.",
    )
    order = args.String(
        aliases=["-s", "--sort"],
        choices=list(ORDER_MAPPING.keys()),
        default="name",
        description=f"""Sort repositories by their value in one of the columns displayed.
        Possible values are {string.join_and(list(ORDER_MAPPING.keys()))}.
        """,
    )

    @property
    def repositories_path(self) -> Path:
        """The directory under which odev clones repositories."""
        return self.config.paths.repositories

    def run(self) -> None:
        with progress.spinner("Listing repositories"):
            paths = self.find_repositories()

            if not paths:
                message = f"No repository found in {self.repositories_path.as_posix()}"

                if self.args.expression:
                    message += f" matching pattern '{self.args.expression.pattern}'"

                raise self.error(message)

            if self.args.names_only:
                self.print("\n".join(paths), highlight=False)
                return

            databases = self.linked_databases()
            repositories = [self.describe(name, path, databases.get(name, [])) for name, path in paths.items()]
            repositories.sort(key=ORDER_MAPPING[self.args.order])
            data = self.get_table_data(repositories)

        self.print()
        self.table(*data, box=None, title=f"Repositories in {self.repositories_path.as_posix()}")

    def find_repositories(self) -> dict[str, Path]:
        """Find the git repositories under the repositories path, at any depth to include the ones cloned
        from hosts other than GitHub as `<host>/<group>/.../<repository>`.

        :return: The paths of the repositories, indexed by their name and sorted.
        :rtype: Dict[str, Path]
        """
        if not self.repositories_path.is_dir():
            return {}

        repositories: dict[str, Path] = {}

        for path in sorted(self.walk_repositories(self.repositories_path)):
            name = path.relative_to(self.repositories_path).as_posix()

            if not self.args.expression or self.args.expression.search(name):
                repositories[name] = path

        return repositories

    def walk_repositories(self, root: Path) -> Iterator[Path]:
        """Walk a directory tree for git repositories, without descending into the repositories found.

        :param root: The directory to walk.
        :return: The paths of the repositories, the root itself excluded.
        :rtype: Iterator[Path]
        """
        for directory, subdirectories, files in os.walk(root):
            if directory != str(root) and (".git" in subdirectories or ".git" in files):
                subdirectories.clear()
                yield Path(directory)

    def linked_databases(self) -> dict[str, list[str]]:
        """List the local databases linked to each repository, ignoring the ones that no longer exist.

        :return: The names of the databases, indexed by the name of the repository they are linked to.
        :rtype: Dict[str, List[str]]
        """
        existing = set(self.list_databases())
        return {
            repository: [database for database in databases if database in existing]
            for repository, databases in self.store.databases.linked_repositories().items()
        }

    def describe(self, name: str, path: Path, databases: list[str]) -> ClonedRepository:
        """Read the git status of a repository.

        :param name: The name of the repository.
        :param path: The local path of the repository.
        :param databases: The local databases linked to the repository.
        :return: The status of the repository.
        :rtype: ClonedRepository
        """
        repository = ClonedRepository(name=name, path=path, databases=databases)

        try:
            repo = Repo(path)
        except (GitCommandError, InvalidGitRepositoryError, NoSuchPathError):
            logger.debug(f"Invalid git repository at {path.as_posix()}")
            repository.branch = "<invalid>"
            return repository

        try:
            # Without optional locks, git does not refresh the index and cannot block a concurrent command
            repository.changes = len(repo.git.status("--porcelain", env={"GIT_OPTIONAL_LOCKS": "0"}).splitlines())

            if not repo.head.is_valid():
                repository.branch = "<empty>"
                return repository

            commit = repo.head.commit
            repository.last_commit = datetime.fromtimestamp(commit.committed_date).astimezone()

            if repo.head.is_detached:
                repository.branch = f"<detached> {commit.hexsha[:8]}"
                return repository

            repository.branch = repo.active_branch.name
            tracking = repo.active_branch.tracking_branch()

            if tracking is not None and tracking.is_valid():
                counts = repo.git.rev_list("--left-right", "--count", f"{tracking.name}...HEAD")
                repository.behind, repository.ahead = (int(count) for count in counts.split())
        except (GitCommandError, ValueError) as error:
            logger.debug(f"Failed to read the status of repository {name!r}: {error}")

        return repository

    def get_table_data(
        self, repositories: list[ClonedRepository]
    ) -> tuple[list[TableHeader], list[list[Any]], list[str]]:
        """Get the table data for the list of repositories."""
        headers = [
            TableHeader(title="Repository"),
            TableHeader(title="Branch"),
            TableHeader(title="Changes", align="right"),
            TableHeader(title="Remote", align="center"),
            TableHeader(title="Last Commit"),
            TableHeader(title="Databases"),
        ]
        rows = [
            [
                repository.name,
                repository.branch,
                string.stylize(str(repository.changes), "color.yellow") if repository.changes else "",
                self.format_remote(repository),
                string.ago(repository.last_commit) if repository.last_commit else "",
                ", ".join(repository.databases),
            ]
            for repository in repositories
        ]
        totals = [f"{len(repositories)} repositories", "", "", "", "", ""]
        return headers, rows, totals

    def format_remote(self, repository: ClonedRepository) -> str:
        """Format the synchronization status of a repository with its tracking branch."""
        if repository.ahead is None or repository.behind is None:
            return string.stylize("no upstream", "color.black")

        if not repository.ahead and not repository.behind:
            return string.stylize("✔", "bold color.green")

        status: list[str] = []

        if repository.ahead:
            status.append(string.stylize(f"↑{repository.ahead}", "color.cyan"))

        if repository.behind:
            status.append(string.stylize(f"↓{repository.behind}", "color.red"))

        return " ".join(status)
