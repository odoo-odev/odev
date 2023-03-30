"""A module for connecting to the Github API and interacting with repositories."""

import re
import shutil
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
    Union,
)

from git import GitCommandError, Remote, RemoteReference, Repo
from github import Github, GithubException

from odev.common import bash
from odev.common.connectors.base import Connector
from odev.common.console import Colors, console
from odev.common.errors import ConnectorError
from odev.common.logging import logging
from odev.common.progress import Progress, spinner
from odev.common.signal_handling import capture_signals


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
            logger.debug(f"Stashing changes in repository {self.repository!r}")
            self.repository.git.stash("save")
            self.stashed = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Pop changes from the repository stash."""
        if any((exc_type, exc_val, exc_tb)):
            return

        if self.stashed:
            logger.debug(f"Restoring stashed changes in repository {self.repository!r}")
            self.repository.git.stash("pop")


class GitWorktree:
    """A dataclass for working with git worktrees."""

    # --- Attributes -----------------------------------------------------------

    connector: "GithubConnector"
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
            (?:branch\s)(?P<ref>refs\/heads\/(?P<branch>.+))?\n?
            (?P<detached>detached)?\n?
            |(?P<bare>bare)?\n?
            |(?P<locked>locked)\s?(?P<locked_reason>.+)?\n?
            |(?P<prunable>prunable)\s?(?P<prunable_reason>.+)?\n?
        )
        """,
        re.VERBOSE | re.MULTILINE,
    )
    """The regex to use to parse the output of `git worktree list --porcelain`."""

    def __init__(
        self,
        connector: "GithubConnector",
        worktree: str,
        ref: str = None,
        branch: str = None,
        commit: str = None,
        bare: bool = False,
        detached: bool = False,
        locked: bool = False,
        locked_reason: str = None,
        prunable: bool = False,
        prunable_reason: str = None,
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
        return f"GitWorktree({self.repository.name} on {self.branch})"

    @property
    def repository(self) -> Repo:
        """Get the repository object for the worktree.

        :return: The repository object.
        :rtype: Repo
        """
        return self.connector

    @classmethod
    def parse(cls, connector: "GithubConnector", entry: str) -> "GitWorktree":
        """Parse an entry from `git worktree list --porcelain` Git worktree.

        :param entry: The entry to parse.
        :return: The Git worktree.
        :rtype: GitWorktree
        """
        matched_values = cls._re_porcelain.search(entry).groupdict()
        values: Mapping[str, Union[str, bool]] = {
            key: bool(value) if key in ("bare", "detached", "locked", "prunable") else value
            for key, value in matched_values.items()
        }
        return cls(connector, **values)  # type: ignore


class GithubConnector(Connector):
    """A class for connecting to the Github API."""

    _token: str = None
    """The Github API token for the current session."""

    _connection: Github = None
    """The connection to the Github API."""

    _token_vault_key: str = "github.com:token"
    """The key to use to store the Github API token in the vault."""

    _organization: str = None
    """The organization to which the repository belongs."""

    _repository: str = None
    """The name of repository to connect to."""

    _requirements_changed: bool = False
    """Whether the requirements.txt file has been modified since the last pull."""

    repository: Repo = None
    """The repository object."""

    def __init__(self, repo: str):
        """Initialize the Github connector.

        :param repo: The repository to connect to in the format `organization/repository`.
        """
        super().__init__()

        repo_values = repo.split("/")

        if len(repo_values) != 2:
            raise ConnectorError(
                f"Invalid repository format: expected 'organization/repository' but received {repo!r}",
                self,
            )

        self._organization, self._repository = repo_values
        self.repository = Repo(self.path) if self.path.exists() and self.path.is_dir() else None

    def __repr__(self) -> str:
        return f"GithubConnector({self.name!r})"

    @property
    def name(self) -> str:
        """The name of the repository."""
        return f"{self._organization}/{self._repository}"

    @property
    def path(self) -> Path:
        """The path to the repository."""
        with self.config:
            return Path(self.config.get("paths", "repositories")) / self.name

    @property
    def url(self) -> str:
        """The URL to the repository."""
        return f"https://github.com/{self.name}"

    @property
    def ssh_url(self) -> str:
        """The SSH URL to the repository."""
        return f"git@github.com:{self.name}.git"

    @property
    def remote(self) -> Optional[Remote]:
        """The reference to the remote of the local repository."""
        if hasattr(self.repository.remotes, "origin"):
            return self.repository.remotes.origin

        if self.repository.remotes:
            return self.repository.remotes[0]

        return None

    @property
    def remote_branch(self) -> Optional[RemoteReference]:
        """Reference to the tracked branch on the remote."""
        if self.remote is None:
            return None

        return self.repository.active_branch.tracking_branch()

    @property
    def default_branch(self) -> Optional[str]:
        """The main branch of the repository."""
        if self.remote is None:
            if not self.repository.heads:
                return None

            return self.repository.heads[0].name.split("/")[-1]

        with self:
            return self._connection.get_repo(self.name).default_branch

    @property
    def branch(self) -> Optional[str]:
        """The current branch of the repository."""
        if self.repository.head.is_detached:
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
        with self.config:
            return Path(self.config.get("paths", "repositories")).parent / ".worktrees"

    def update(self):
        """Update the repository."""
        if self.repository and self.remote:
            self.pull()
            self.fetch()
            self.prune_worktrees()
            self.fetch_worktrees()

    def connect(self):
        """Connect to the Github API."""
        if self._token is None:
            self._token = self.store.secrets.get(
                key=self._token_vault_key,
                fields=("password",),
                prompt_format="Please enter your Github API token:",
            ).password

        if self._connection is None:
            self._connection = Github(self._token)

        if not self.authenticated:
            logger.warning("Failed to connect to Github API, please check your token is valid")
            self.store.secrets.invalidate(self._token_vault_key)
            self._disconnect()
            return self.connect()

        if self.repository is None and self.path.exists() and self.path.is_dir():
            self.repository = Repo(self.path)

        logger.debug("Connected to Github API")

    def disconnect(self):
        """Disconnect from the Github API."""
        self._disconnect()
        logger.debug("Disconnected from Github API")

    def _disconnect(self):
        """Disconnect from the Github API."""
        self._token = None
        self._connection = None
        del self._connection

    def fetch(self):
        """Fetch changes from the remote in a detached process.
        Doesn't wait for the fetch to end so pulling right after calling this method
        may result in changes not being downloaded.
        Attention: Do not call right before `pull` as both git processes might enter into conflict.
        """
        bash.detached(f"cd {self.path} && git fetch")

    def clone(self, branch: str = None):
        """Clone the repository locally."""
        if self.path.exists():
            return

        options = ["--recurse-submodules"]

        if branch is not None:
            options.extend(["--branch", branch, "--single-branch"])

        logger.debug(f"Cloning repository {self.name!r} to {self.path}" + (f" on branch {branch!r}" if branch else ""))
        self._git_progress(Repo.clone_from, self.ssh_url, self.path, multi_options=options)
        self.repository = Repo(self.path)
        logger.info(
            f"Cloned repository [bold {Colors.CYAN}]{self.name!s}[/bold {Colors.CYAN}]"
            + (f" on branch {branch!r}" if branch else "")
        )

    def pull(self, force: bool = False):
        """Pull the latest modifications from the remote repository."""
        if not self.has_pending_changes():
            return False

        logger.info(f"Repository {self.name!r} has pending changes on branch {self.branch!r}")
        self.check_requirements()

        if force or console.confirm("Pull changes now?", True):
            with Stash(self.repository):
                self._git_progress(self.remote.pull, ff_only=True)

    def checkout(self, branch: str = None):
        """Checkout a branch in the repository."""
        if branch is None:
            branch = self.default_branch

        logger.debug(f"Checking out branch {branch!r} in repository {self.name!r}")
        self.repository.git.checkout(branch, quiet=True)

    def has_pending_changes(self):
        """Check whether the current branch in the repository has pending changes ready to be pulled."""
        if self.remote_branch is None:
            return False

        rev_list: str = self.repository.git.rev_list("--left-right", "--count", "@{u}...HEAD")
        commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split("\t")]
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
        requirements_file = self.path / "requirements.txt"

        diff = self.repository.git.diff("--name-only", "HEAD", "--", requirements_file).strip()

        if diff == requirements_file.as_posix():
            logger.debug(
                f"Repository [bold {Colors.CYAN}]{self.name}[/bold {Colors.CYAN}] "
                "requirements have changed since last version"
            )

        self._requirements_changed = bool(diff)

    def _git_progress(self, operation: Callable, *args, **kwargs):
        """Display a progress bar when performing time-consuming git operations."""
        progress = Progress()
        repo_name = f"[bold {Colors.CYAN}]{self.name}[/bold {Colors.CYAN}]"
        task_description_clone = f"Downloading repository {repo_name}"
        task_description_delta = f"Resolving deltas in {repo_name}"
        task = progress.add_task(task_description_clone, total=None, start=False)

        def update_progress(operation_code: int, current_count: int, max_count: int = None, message: str = None):
            if operation_code == 66:
                progress.stop_task(task)
                progress.stop()
                logger.debug(f"Cloned repository {repo_name}")
                return
            elif operation_code == 33:
                progress.start_task(task)
            elif operation_code == 65:
                progress.update(task, description=task_description_delta)

            progress.update(task, total=max_count, completed=current_count)

        def signal_handler_progress(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
            progress.stop_task(task)
            progress.stop()
            logger.warning(f"{task_description_clone}: task interrupted by user")
            raise KeyboardInterrupt

        progress.start()

        with capture_signals(handler=signal_handler_progress):
            try:
                return operation(*args, **kwargs, progress=update_progress)
            except GitCommandError:
                pass

    def worktrees(self) -> Generator[GitWorktree, None, None]:
        """Iterate over the working trees of the git repository."""
        tree_list: str = self.repository.git.worktree("list", "--porcelain")

        for worktree in [tree.strip() for tree in tree_list.split("\n" * 2) if tree and tree.startswith("worktree ")]:
            yield GitWorktree.parse(self, worktree)

    def create_worktree(self, path: Union[Path, str], branch: str = None):
        """Create a new worktree for the repository based on a specific branch
        or the default branch of the repository.

        :param path: Path to the worktree.
        :param branch: Branch to create the worktree from. Defaults to the main branch of the repository.
        """
        if branch is None:
            branch = self.default_branch

        if isinstance(path, str):
            path = Path(path)

        if not path.is_absolute():
            path = (self.worktrees_path / path).resolve()

        message = f"worktree [bold]{branch!s}[/bold] for [bold {Colors.CYAN}]{self.name}[/bold {Colors.CYAN}]"

        with spinner(f"Creating {message}"):
            self.worktrees_path.mkdir(parents=True, exist_ok=True)

            if path.exists():
                logger.debug(f"Old worktree {path!s} for repository {self.name!r} exists, removing it")
                shutil.rmtree(path)

            logger.debug(f"Creating worktree {path!s} for repository {self.name!r} on branch {branch!r}")

            try:
                self.repository.git.worktree("add", path, branch or self.branch)
            except GitCommandError as error:
                if "fatal: invalid reference" in error.stderr:
                    logger.error(f"Git branch {branch!r} does not exist for repository {self.name!r}")
                    raise ConnectorError("Did you forget to use '--version master'?", self) from error

                raise error

        logger.info(f"Created {message}")

    def prune_worktrees(self):
        """Prune worktrees marked as prunable by git."""
        if any(worktree.prunable for worktree in self.worktrees()):
            logger.debug(f"Pruning worktrees for repository {self.name!r}")
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

    def get_worktree(self, branch: str, create: bool = True) -> Optional[GitWorktree]:
        """Find a worktree based on a branch and create it if needed.

        :param branch: Branch to find a worktree for.
        :param create: Whether to create the worktree if it does not exist.
        :return: A worktree that belongs to the current repository and is based on the specified branch.
        :rtype: Optional[GitWorktree]
        """
        for worktree in self.worktrees():
            if not worktree.path.is_dir():
                logger.debug(f"Worktree path {worktree.path!s} does not exist, removing references")
                self.repository.git.worktree("remove", worktree.path)
                continue

            if worktree.branch == branch:
                return worktree

        if create:
            self.create_worktree(f"{branch}/{self._repository}", branch)
            return self.get_worktree(branch, create=create)

        return None

    def fetch_worktrees(self, worktrees: Sequence[GitWorktree] = None):
        """Fetch all worktrees of the repository.
        Attention: Do not call right before `pull_worktrees` as both git processes might enter into conflict.

        :param worktrees: A list of worktrees to fetch. If not specified, all worktrees will be fetched.
        """
        for worktree in self._filter_worktrees(worktrees):
            logger.debug(f"Fetching changes in worktree {worktree.path!s}")
            bash.detached(f"cd {worktree.path!s} && git fetch")

    def pull_worktrees(self, worktrees: Sequence[GitWorktree] = None):
        """Pull all worktrees of the repository.

        :param worktrees: A list of worktrees to pull. If not specified, all worktrees will be pulled.
        """
        for worktree in self._filter_worktrees(worktrees):
            repo = Repo(worktree.path)
            rev_list: str = repo.git.rev_list("--left-right", "--count", "@{u}...HEAD")
            commits_behind = int(rev_list.split("\t")[0])
            logger.debug(f"Worktree at {worktree.path!s} is {commits_behind} commits behind 'origin/{worktree.branch}'")

            if commits_behind:
                with Stash(repo):
                    logger.debug(f"Pulling changes in worktree {worktree.path!s}")
                    repo.git.pull("origin", worktree.branch, ff_only=True, quiet=True)
