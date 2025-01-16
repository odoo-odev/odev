"""A module for connecting to the Github API and interacting with repositories."""

import re
import shutil
from functools import lru_cache
from pathlib import Path
from types import FrameType
from typing import (
    Callable,
    ClassVar,
    Generator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)
from urllib.parse import urlparse

from git import GitCommandError, Remote, RemoteReference, Repo
from github import Auth as GithubAuth, Github, GithubException

from odev.common import bash, progress, string
from odev.common.connectors.base import Connector
from odev.common.console import console
from odev.common.errors import ConnectorError
from odev.common.logging import logging, silence_loggers
from odev.common.progress import Progress, spinner
from odev.common.signal_handling import capture_signals


GITHUB_DOMAIN = "github.com"
"""The domain of the GitHub API."""


logger = logging.getLogger(__name__)


class Stash:
    """A context manager for stashing and popping changes in a git repository."""

    # --- Low-level methods ----------------------------------------------------

    def __init__(self, repository: Repo):
        """Initialize the Git stash context manager.

        :param repository: The repository to stash changes in.
        """

        self.repository: Repo = repository
        """The repository to stash changes in."""

        self.stashed: bool = False
        """Whether changes have been stashed in the repository."""

    def __enter__(self):
        """Stash changes in the repository."""
        if self.repository.is_dirty():
            logger.debug(f"Stashing changes in repository {self.repository.working_dir!r}")
            self.repository.git.stash("save")
            self.stashed = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Pop changes from the repository stash."""
        if any((exc_type, exc_val, exc_tb)):
            return

        if self.stashed:
            logger.debug(f"Restoring stashed changes in repository {self.repository.working_dir!r}")
            self.repository.git.stash("pop")


class GitWorktree:
    """A dataclass for working with git worktrees."""

    # --- Attributes -----------------------------------------------------------

    connector: "GitConnector"
    """The connector to use to connect to the Github API."""

    path: Path
    """The path of the worktree."""

    ref: str
    """The ref of the worktree."""

    branch: str
    """The branch the worktree is attached to."""

    commit: str
    """The commit the worktree is on."""

    bare: bool = False
    """Whether the worktree is bare."""

    detached: bool = False
    """Whether the worktree is detached."""

    locked: bool = False
    """Whether the worktree is locked.
    See https://git-scm.com/docs/git-worktree#Documentation/git-worktree.txt-lock
    """

    locked_reason: Optional[str] = None
    """The reason why the worktree is locked."""

    prunable: bool = False
    """Whether the worktree is prunable.
    See https://git-scm.com/docs/git-prune
    """

    prunable_reason: Optional[str] = None
    """The reason why the worktree is prunable."""

    _re_porcelain: ClassVar[re.Pattern[str]] = re.compile(
        r"""
        (?:
            (?:worktree\s)(?P<worktree>\/.+)?\n?
            (?:HEAD\s)(?P<commit>[a-f0-9]{40})?\n?
            (?:(?:branch\s)(?P<ref>refs\/heads\/(?P<branch>.+))\n?)?
            (?:(?P<detached>detached)\n?)?
            (?:(?P<bare>bare)\n?)?
            (?:(?P<locked>locked)\s?(?P<locked_reason>.+)?\n?)?
            (?:(?P<prunable>prunable)\s?(?P<prunable_reason>.+)?\n?)?
        )
        """,
        re.VERBOSE | re.MULTILINE,
    )
    """The regex to use to parse the output of `git worktree list --porcelain`."""

    def __init__(
        self,
        connector: "GitConnector",
        worktree: str,
        ref: str,
        branch: str,
        commit: str,
        bare: bool = False,
        detached: bool = False,
        locked: bool = False,
        locked_reason: Optional[str] = None,
        prunable: bool = False,
        prunable_reason: Optional[str] = None,
    ):
        """Initialize the Git worktree.

        :param connector: The connector to use to connect to the Github API.
        :param worktree: The path of the worktree.
        :param branch: The branch of the worktree.
        :param commit: The commit of the worktree.
        """
        self.connector = connector
        self.path = Path(worktree)
        self.ref = ref
        self.branch = branch
        self.commit = commit
        self.bare = bare
        self.detached = detached
        self.locked = locked
        self.locked_reason = locked_reason
        self.prunable = prunable
        self.prunable_reason = prunable_reason

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, GitWorktree) and self.path == __o.path

    def __repr__(self) -> str:
        return f"GitWorktree(name={self.name!r}, repository={self.connector.name!r}, revision='{self.branch or self.commit}')"

    @property
    def name(self):
        """The name of the worktree."""
        return self.path.parent.name if self.connector.odev.worktrees_path in self.path.parents else "master"

    @property
    def repository(self) -> Repo:
        """Get the repository object for the worktree.

        :return: The repository object.
        :rtype: Repo
        """
        return Repo(self.path)

    @classmethod
    def parse(cls, connector: "GitConnector", entry: str) -> "GitWorktree":
        """Parse an entry from `git worktree list --porcelain` Git worktree.

        :param entry: The entry to parse.
        :return: The Git worktree.
        :rtype: GitWorktree
        """
        matched_values = cast(re.Match[str], cls._re_porcelain.search(entry)).groupdict()
        values: Mapping[str, Union[str, bool]] = {
            key: bool(value) if key in ("bare", "detached", "locked", "prunable") else value
            for key, value in matched_values.items()
        }
        return cls(connector, **values)  # type: ignore

    def pending_changes(self) -> Tuple[int, int]:
        """Check for changes in the worktree and return a tuple of commits behind and ahead.
        :return: A tuple of commits behind and ahead.
        :rtype: Tuple[int, int]
        """
        repo = Repo(self.path)
        rev_list: str = repo.git.rev_list("--left-right", "--count", "@{u}...HEAD")
        commits_behind, commits_ahead = [int(commits) for commits in rev_list.split("\t")]
        return commits_behind, commits_ahead


class GitConnector(Connector):
    """A class for connecting to the Github API."""

    _token: Optional[str] = None
    """The Github API token for the current session."""

    _connection: Optional[Github] = None
    """The connection to the Github API."""

    _organization: str
    """The organization to which the repository belongs."""

    _repository: str
    """The name of repository to connect to."""

    _requirements_changed: bool = False
    """Whether the requirements.txt file has been modified since the last pull."""

    def __init__(self, repo: str, path: Optional[Path] = None):
        """Initialize the Github connector.
        :param repo: The repository to connect to in the format `organization/repository`.
        :param path: The path to the repository, inferred from the Odev config if omitted.
        """
        super().__init__()

        self._path: Optional[Path] = path
        """Forced path to the git repository on the local system."""

        if "@" in repo and ":" in repo:  # Assume the repo is in the format git@github.com:organization/repository.git
            repo = repo.split(":")[-1]

        repo = urlparse(repo).path.removeprefix("/").removesuffix(".git")
        repo_values = repo.split("/")

        if len(repo_values) != 2:
            raise ConnectorError(
                "Invalid repository format: expected a valid git URL or repository name in one of the formats:\n"
                + string.join_bullet(
                    [
                        string.stylize(url, "color.purple")
                        for url in (
                            "organization/repository",
                            "https://github.com/organization/repository",
                            "git@github.com:organization/repository.git",
                        )
                    ],
                ),
                self,
            )

        self._organization, self._repository = repo_values

    def __repr__(self) -> str:
        return f"GitConnector({self.name!r})"

    def __eq__(self, __o) -> bool:
        return isinstance(__o, GitConnector) and self.name == __o.name

    def __hash__(self) -> int:
        return hash(self.name)

    @property
    def name(self) -> str:
        """The name of the repository."""
        return f"{self._organization}/{self._repository}"

    @property
    def path(self) -> Path:
        """The path to the repository."""
        return self._path or self.config.paths.repositories / self.name

    @property
    def exists(self) -> bool:
        """Whether the repository exists locally."""
        return self.path.is_dir() and self.path / ".git" in self.path.iterdir()

    @property
    def url(self) -> str:
        """The URL to the repository."""
        return f"https://{GITHUB_DOMAIN}/{self.name}"

    @property
    def ssh_url(self) -> str:
        """The SSH URL to the repository."""
        return f"git@{GITHUB_DOMAIN}:{self.name}.git"

    @property
    def repository(self) -> Optional[Repo]:
        """The repository object."""
        return Repo(self.path) if self.exists else None

    @property
    def remote(self) -> Optional[Remote]:
        """The reference to the remote of the local repository."""
        if self.repository is None:
            return None

        if hasattr(self.repository.remotes, "origin"):
            return self.repository.remotes.origin

        if self.repository.remotes:
            return self.repository.remotes[0]

        return None

    @property
    def remote_branch(self) -> Optional[RemoteReference]:
        """Reference to the tracked branch on the remote."""
        if self.repository is None or self.remote is None:
            return None

        return self.repository.active_branch.tracking_branch()

    @property
    def default_branch(self) -> Optional[str]:
        """The main branch of the repository."""
        if self.repository is None:
            return None

        if self.remote is None:
            if not self.repository.heads:
                return None

            return self.repository.heads[0].name.split("/")[-1]

        with self:
            return cast(Github, self._connection).get_repo(self.name).default_branch

    @property
    def branch(self) -> Optional[str]:
        """The current branch of the repository."""
        if self.repository is None or self.repository.head.is_detached:
            return None

        return self.repository.active_branch.name.split("/")[-1]

    @property
    def requirements_path(self) -> Path:
        """Path to the requirements.txt path of the repo, if present."""
        return self.path / "requirements.txt"

    @property
    def authenticated(self) -> bool:
        """Whether the current session is authenticated."""
        if self._connection is None:
            return False

        try:
            self._connection.get_user().login
        except GithubException:
            return False
        else:
            return True

    @property
    def worktrees_path(self) -> Path:
        """Path to the worktrees directory."""
        return self.odev.home_path / "worktrees"

    def update(self):
        """Update the repository."""
        if self.repository and self.remote:
            self.prune_worktrees()
            self.pull()
            self.fetch()
            self.fetch_worktrees()

    def connect(self):
        """Connect to the Github API."""
        if self._token is None:
            self._token = self.store.secrets.get(
                GITHUB_DOMAIN,
                scope="api",
                fields=["password"],
                prompt_format="GitHub API token:",
            ).password

        if not self.connected:
            self._connection = Github(auth=GithubAuth.Token(self._token))  # type: ignore [assignment]

        if not self.authenticated:
            logger.warning("Failed to connect to Github API, please check your token is valid")
            self.store.secrets.invalidate(GITHUB_DOMAIN, scope="api")
            self._disconnect()
            return self.connect()

        logger.debug("Connected to Github API")

    def disconnect(self):
        """Disconnect from the Github API."""
        self._disconnect()
        logger.debug("Disconnected from Github API")

    def _disconnect(self):
        """Disconnect from the Github API."""
        self._token = None
        del self._connection

    def _check_repository(self):
        """Check whether the repository exists locally."""
        if self.repository is None:
            raise ConnectorError(f"Repository {self.name!r} does not exist", self)

    def fetch(self):
        """Fetch changes from the remote in a detached process.
        Doesn't wait for the fetch to end so pulling right after calling this method
        may result in changes not being downloaded.
        Attention: Do not call right before `pull` as both git processes might enter into conflict.
        """
        bash.detached(f"cd {self.path} && git fetch")

    def _get_clone_options(self, revision: Optional[str] = None) -> List[str]:
        """Get the options to use when cloning the repository, passed through to git.
        :param revision: The revision to checkout when cloning the repository.
        """
        options = ["--recurse-submodules"]

        if revision is not None:
            options.extend(["--branch", revision])

        return options

    def clone(self, revision: Optional[str] = None):
        """Clone the repository locally.
        :param revision: The revision to checkout when cloning the repository.
        """
        if self.path.exists():
            if revision is not None:
                self.checkout(revision)

            return logger.debug(f"Repository {self.name!r} already cloned to {self.path.as_posix()}")

        logger.debug(
            f"Cloning repository {self.name!r} to {self.path}" + (f" on revision {revision!r}" if revision else "")
        )

        try:
            self._git_progress(
                Repo.clone_from,
                self.ssh_url,
                self.path,
                multi_options=self._get_clone_options(revision),
            )
        except GitCommandError as error:
            message: str = f"Failed to clone repository {self.name!r} to {self.path}"

            if error.stderr:
                message += f": {error.stderr}"

            raise ConnectorError(message, self) from error
        else:
            logger.info(
                f"Cloned repository {self.name!r} to {self.path.as_posix()}"
                + (f" on revision {revision!r}" if revision else "")
            )

    def pull(self, force: bool = False) -> None:
        """Pull the latest modifications from the remote repository.
        :param force: Whether to force the pull operation.
        """
        if self.repository is None or self.remote is None or not self.has_pending_changes():
            return

        logger.info(f"Repository {self.name!r} has pending changes on revision {self.branch!r}")
        self.check_requirements()

        if force or console.confirm("Pull changes now?", default=True):
            try:
                with Stash(self.repository):
                    self._git_progress(self.remote.pull, ff_only=True)
            except GitCommandError as error:
                message: str = f"Failed to pull changes in repository {self.name!r}"

                if error.stderr:
                    message += f": {error.stderr}"

                raise ConnectorError(message, self) from error

    def checkout(self, revision: Optional[str] = None, quiet: bool = False) -> None:
        """Checkout a branch in the repository.
        :param revision: The revision to checkout. Defaults to the main branch of the repository.
        :param quiet: Do not log checkout status.
        """
        self._check_repository()
        assert self.repository is not None

        if revision is None:
            revision = self.default_branch

        if revision == self.branch:
            return logger.debug(f"Revision {revision!r} already checked out in repository {self.name!r}")

        logger.debug(f"Checking out revision {revision!r} in repository {self.name!r}")

        try:
            self.repository.git.checkout(revision, quiet=True)
        except GitCommandError as error:
            message: str = f"Failed to checkout revision {revision!r} in repository {self.name!r}"

            if error.stderr:
                message += f": {error.stderr}"

            raise ConnectorError(message, self) from error
        else:
            if not quiet:
                logger.info(f"Checked out revision {revision!r} in repository {self.name!r}")

    def pending_changes(self) -> Tuple[int, int]:
        """Get the number of pending commits to be pulled and pushed.
        :return: A tuple of the number of commits behind and the number of commits ahead.
        :rtype: Tuple[int, int]
        """
        if self.repository is None or self.remote_branch is None:
            return 0, 0

        rev_list: str = self.repository.git.rev_list("--left-right", "--count", "@{u}...HEAD")
        commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split("\t")]
        return commits_behind, commits_ahead

    def has_pending_changes(self):
        """Check whether the current branch in the repository has pending changes ready to be pulled."""
        if self.remote_branch is None or self.remote is None:
            return False

        commits_behind, commits_ahead = self.pending_changes()
        message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
        message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"
        message_repo = f"Repository {self.name!r}"

        if commits_behind and commits_ahead:
            logger.debug(f"{message_repo} is {message_behind} and {message_ahead} {self.remote.name}")
        elif commits_behind:
            logger.debug(f"{message_repo} is {message_behind} {self.remote.name}")
        elif commits_ahead:
            logger.debug(f"{message_repo} is {message_ahead} {self.remote.name}")
        else:
            logger.debug(f"{message_repo} is up-to-date with {self.remote.name}")

        if commits_ahead:
            return False

        return bool(commits_behind)

    def check_requirements(self):
        """Check whether a requirements.txt file exists in the current repository and if has been modified
        since the last pull.
        """
        if self.repository is None:
            self._requirements_changed = False
            return

        requirements_file = self.path / "requirements.txt"

        diff = self.repository.git.diff("--name-only", "HEAD", "--", requirements_file).strip()

        if diff == requirements_file.as_posix():
            logger.debug(f"Repository {self.name!r} requirements have changed since last version")

        self._requirements_changed = bool(diff)

    def _git_progress(self, operation: Callable, *args, **kwargs):
        """Display a progress bar when performing time-consuming git operations."""
        progress = Progress()
        task_description_clone = f"Downloading repository {self.name!r}"
        task_description_delta = f"Resolving deltas in {self.name!r}"
        task = progress.add_task(task_description_clone, total=None, start=False)

        def update_progress(
            operation_code: int, current_count: int, max_count: Optional[int] = None, message: Optional[str] = None
        ):
            if operation_code == 66:
                progress.stop_task(task)
                progress.stop()
                logger.debug(f"Cloned repository {self.name!r}")
                return
            elif operation_code == 33:
                progress.start_task(task)
            elif operation_code == 65:
                progress.update(task, description=task_description_delta)

            progress.update(task, total=max_count, completed=current_count)

        def signal_handler_progress(
            signal_number: int, frame: Optional[FrameType] = None, message: Optional[str] = None
        ):
            progress.stop_task(task)
            progress.stop()
            logger.warning(f"{task_description_clone}: task interrupted by user")
            raise KeyboardInterrupt

        progress.start()

        with capture_signals(handler=signal_handler_progress):
            try:
                result = operation(*args, **kwargs, progress=update_progress)
            except GitCommandError as error:
                progress.stop_task(task)
                progress.stop()
                raise error
            else:
                progress.stop_task(task)
                progress.stop()
                return result

    def worktrees(self) -> Generator[GitWorktree, None, None]:
        """Iterate over the working trees of the git repository."""
        if self.repository is None:
            return

        tree_list: str = self.repository.git.worktree("list", "--porcelain")

        for worktree in [tree.strip() for tree in tree_list.split("\n" * 2) if tree and tree.startswith("worktree ")]:
            yield GitWorktree.parse(self, worktree)

    def _resolve_worktree_path(self, path: Union[Path, str]) -> Path:
        """Resolve the path of a worktree.
        :param path: Path to the worktree.
        """
        if isinstance(path, str):
            path = Path(path)

        if not path.is_absolute():
            path = (self.worktrees_path / path).resolve()

        return path

    def create_worktree(self, path: Union[Path, str], revision: Optional[str] = None):
        """Create a new worktree for the repository based on a specific revision or the default branch
        of the repository.
        :param path: Path to the worktree.
        :param revision: Revision to create the worktree from (branch or commit SHA). Defaults to the main branch
        of the repository.
        """
        self._check_repository()
        assert self.repository is not None
        path = self._resolve_worktree_path(path)
        revision = revision or self.default_branch or self.branch

        if path.exists():
            logger.debug(f"Old worktree {path!s} for repository {self.name!r} exists, removing it")

            try:
                self.repository.git.worktree("remove", path, "--force")
            except GitCommandError:
                logger.debug(
                    f"Failed to remove worktree {path!s} for repository {self.name!r}: "
                    "directory exists but is not registered as a worktree"
                )

            shutil.rmtree(path, ignore_errors=True)

        message = f"worktree {path.parent.name!r} for {self.name!r} in version {revision!r}"

        with spinner(f"Creating {message}"):
            logger.debug(f"Creating worktree {path!s} for repository {self.name!r} on branch {revision!r}")
            self.worktrees_path.mkdir(parents=True, exist_ok=True)

            try:
                self.repository.git.fetch("origin", revision)
                self.repository.git.worktree("add", path, revision, "--force")
            except GitCommandError as error:
                if "fatal: invalid reference" in error.stderr:
                    logger.warning(f"Git ref {revision!r} does not exist for repository {self.name!r}")

                    if revision and not revision.startswith("origin/"):
                        return self.create_worktree(path, f"origin/{revision}")

                    raise ConnectorError("Did you forget to use '--version master'?", self) from error

                raise error

        logger.info(f"Created {message} in {path.as_posix()}")

    def remove_worktree(self, path: Union[Path, str]):
        """Remove a worktree from the repository.
        :param path: Path to the worktree.
        """
        self._check_repository()
        assert self.repository is not None
        path = self._resolve_worktree_path(path)

        if not path.exists():
            return logger.debug(f"Worktree {path!s} for repository {self.name!r} does not exist")

        message = f"worktree {path.parent.name!r} for {self.name!r}"

        with spinner(f"Removing {message}"):
            logger.debug(f"Removing worktree {path!s} for repository {self.name!r}")
            self.repository.git.worktree("remove", path, "--force")
            shutil.rmtree(path, ignore_errors=True)

        logger.info(f"Removed {message} in {path.as_posix()}")

    def checkout_worktree(self, path: Union[Path, str], revision: Optional[str] = None):
        """Checkout a specific revision in an existing worktree.
        :param path: Path to the worktree.
        :param revision: Revision to checkout in the worktree (branch or commit SHA). Defaults to the default branch
        of the repository.
        """
        self._check_repository()
        assert self.repository is not None
        path = self._resolve_worktree_path(path)

        if not path.exists():
            return logger.debug(f"Worktree {path!s} for repository {self.name!r} does not exist")

        worktree = next((worktree for worktree in self.worktrees() if worktree.name == path.parent.name), None)

        if worktree is None:
            raise ConnectorError(f"Worktree {path.parent.name!r} for repository {self.name!r} does not exist", self)

        if revision in (worktree.branch, worktree.commit):
            return logger.info(
                f"Worktree {path.parent.name!r} in repository {self.name!r} is already on revision {revision!r}"
            )

        message = f"revision {revision!r} in worktree {path.parent.name!r} for {self.name!r}"

        with spinner(f"Checking out {message}"), silence_loggers("odev.common.connectors.git"):
            worktree.connector.remove_worktree(path)
            worktree.connector.create_worktree(path, revision)

        logger.info(f"Checked out {message} in {path.as_posix()}")

    def prune_worktrees(self):
        """Prune worktrees marked as prunable by git."""
        self._check_repository()
        assert self.repository is not None

        if any(worktree.prunable for worktree in self.worktrees()):
            prunable = [
                f"{self.name!r} on branch {worktree.branch!r}: {worktree.prunable_reason or 'unknown reason'}"
                for worktree in self.worktrees()
                if worktree.prunable
            ]

            logger.warning(f"Pruning worktrees for repository {self.name!r}:\n{string.join_bullet(prunable)}")
            self.repository.git.worktree("prune")

    def _filter_worktrees(self, worktrees: Sequence[GitWorktree]) -> List[GitWorktree]:
        """Filter a list of worktrees based on the current repository.
        :param worktrees: A list of worktrees to filter.
        :return: A list of worktrees that belong to the current repository, filtered.
        :rtype: List[GitWorktree]
        """
        if worktrees is None:
            return list(self.worktrees())

        return [worktree for worktree in self.worktrees() if worktree in worktrees]

    @lru_cache
    def _get_worktree(self, branch: str) -> Optional[GitWorktree]:
        """Find a worktree based on a branch.
        :param branch: Branch to find a worktree for.
        :return: A worktree that belongs to the current repository and is based on the specified branch.
        :rtype: Optional[GitWorktree]
        """
        for worktree in self.worktrees():
            if worktree.branch == branch:
                return worktree
            elif worktree.path.parent.name == branch:
                message = f"Worktree {self.name!r} for version {branch!r} "

                if worktree.detached:
                    message += f"is detached and points to commit {worktree.commit!r}"
                else:
                    message += f"is targeting another branch {worktree.branch!r}"

                logger.warning(message)
                return worktree

        return None

    def get_worktree(self, branch: str, create: bool = True) -> Optional[GitWorktree]:
        """Find a worktree based on a branch and create it if needed.

        :param branch: Branch to find a worktree for.
        :param create: Whether to create the worktree if it does not exist.
        :return: A worktree that belongs to the current repository and is based on the specified branch.
        :rtype: Optional[GitWorktree]
        """
        self._check_repository()
        assert self.repository is not None
        worktree = self._get_worktree(branch)

        if not worktree and create:
            self.create_worktree(f"{branch}/{self._repository}", branch)
            return self.get_worktree(branch, create=create)

        return worktree

    def fetch_worktrees(self, worktrees: Optional[Sequence[GitWorktree]] = None):
        """Fetch all worktrees of the repository.
        Attention: Do not call right before `pull_worktrees` as both git processes might enter into conflict.

        :param worktrees: A list of worktrees to fetch. If not specified, all worktrees will be fetched.
        """
        for worktree in self._filter_worktrees(worktrees or []):
            logger.debug(f"Fetching changes in worktree {worktree.path!s}")
            bash.detached(f"cd {worktree.path!s} && git fetch")

    def pull_worktrees(self, worktrees: Optional[Sequence[GitWorktree]] = None, force: bool = False):
        """Pull all worktrees of the repository.

        :param worktrees: A list of worktrees to pull. If not specified, all worktrees will be pulled.
        """
        for worktree in self._filter_worktrees(worktrees or []):
            commits_behind, _ = worktree.pending_changes()
            logger.debug(f"Worktree at {worktree.path!s} is {commits_behind} commits behind 'origin/{worktree.branch}'")

            if commits_behind:
                if not force:
                    logger.info(f"Repository {self.name!r} on version {worktree.branch!r} has pending changes")

                    if not console.confirm("Pull changes now?", default=True):
                        continue

                with Stash(worktree.repository), progress.spinner(f"Pulling changes in worktree {worktree.path!s}"):
                    logger.debug(f"Pulling changes in worktree {worktree.path!s}")

                    try:
                        worktree.repository.git.pull("origin", worktree.branch, ff_only=True, quiet=True)
                    except GitCommandError as error:
                        logger.error(f"Failed to pull changes in worktree {worktree.path!s}:\n{error.args[2].decode()}")

    def list_remote_branches(self) -> List[str]:
        """List all remote branches of the repository.

        :return: A list of all remote branches of the repository.
        :rtype: List[str]
        """
        with self:
            branches = cast(Github, self._connection).get_repo(self.name).get_branches()

        return [branch.name for branch in branches]
