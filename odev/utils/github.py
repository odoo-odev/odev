import os
import os.path
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from logging import getLevelName
from typing import (
    Callable,
    ContextManager,
    Dict,
    List,
    Optional,
    Set,
    Union,
)

import git
import git.repo.base
import git.repo.fun
from git import (
    CommandError,
    GitCommandError,
    InvalidGitRepositoryError,
    NoSuchPathError,
    Remote,
    Repo,
)
from git.types import PathLike
from github import Github

from odev.constants import DEFAULT_DATETIME_FORMAT
from odev.exceptions import CommandAborted, HeadRefMismatch, MissingRemote, MissingTrackingBranch
from odev.utils import logging
from odev.utils.config import ConfigManager
from odev.utils.credentials import CredentialsHelper
from odev.utils.python import install_packages


_logger = logging.getLogger(__name__)


_just_fetched_repos: Set[str] = set()


# --- PATCH GitPython to enable relative paths in worktrees --- #

_find_worktree_git_dir__original = git.repo.fun.find_worktree_git_dir


def _find_worktree_git_dir__patched(dotgit: PathLike) -> Optional[str]:
    """
    Patched version of :func:`git.repo.fun.find_worktree_git_dir` that fixes relative
    ``gitdir`` paths specifications in ``.git`` from worktrees.
    The original version returns the relative path which gets then normalized to cwd
    instead of the ``.git`` parent path, generating a wrong worktree path, therefore
    failing to load ``commondir``, basically not finding the original ``.git`` dir.
    """
    value: Optional[str] = _find_worktree_git_dir__original(dotgit)

    if value and not os.path.isabs(value):
        curpath = os.path.dirname(dotgit)
        value = os.path.abspath(os.path.join(curpath, value))

    return value


git.repo.fun.find_worktree_git_dir = _find_worktree_git_dir__patched
git.repo.base.find_worktree_git_dir = _find_worktree_git_dir__patched  # direct import

# --- PATCH END --- #


def get_github(token: Optional[str] = None) -> Github:
    """
    Gets a `Github` instance from the given token, or using a stored or prompted one
    """
    with CredentialsHelper() as creds:
        token = creds.secret("github.token", "Github token:", token)
        github: Github = Github(token)
        _ = github.get_user().login  # will raise with bad credentials
        return github


def repo_name_to_title(repo_name: str) -> str:
    """Beautify a repo name, for unknown reasons"""
    if "/" in repo_name:
        repo_name = repo_name.split("/")[-1]
    return repo_name.replace("-", " ").replace("_", " ").title()


def is_git_repo(path: str) -> bool:
    """
    Check if the given path is part of a valid git repository.
    (N.B. a valid path could also be a subpath of a repository)

    :param path: the path to check
    :return: True if path is a repo, False otherwise
    """
    try:
        Repo(path)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False
    return True


def git_clone(
    parent_dir: str,
    repo_name: str,
    branch: Optional[str] = None,
    *,
    organization: str = "odoo",
    title: Optional[str] = None,
    repo_dir_name: Optional[str] = None,
) -> None:
    """
    Clones a repository from odoo's GitHub.

    :param parent_dir: the parent directory where the repo directory is to be created.
    :param repo_name: the name of the repo in the specified organization on GitHub,
        and the name of the directory within ``parent_dir`` where it will be cloned.
    :param branch: if specified, checkout the repo at the given branch.
    :param organization: the organization/user on GitHub where to find the repo.
        Ignored if specified in ``repo_name``, otherwise defaults to ``odoo``.
    :param title: an optional alternative name to display in the logger for the repo.
    """
    url_path: str
    if "/" in repo_name:
        url_path = repo_name
        repo_name = repo_name.split("/")[-1]
    else:
        url_path = f"{organization}/{repo_name}"

    if repo_dir_name:
        repo_name = repo_dir_name

    _logger.info(f"Cloning {title or repo_name}" + (f" on branch {branch}" if branch else ""))
    clone_options: List[str] = ["--recurse-submodules"]

    if branch:
        clone_options += [f"--branch {branch}"]

    Repo.clone_from(
        f"git@github.com:{url_path}.git",
        f"{parent_dir}/{repo_name}",
        multi_options=clone_options,
    )


def git_clone_if_missing(
    parent_dir: str,
    repo_name: str,
    branch: Optional[str] = None,
    title: Optional[str] = None,
    force: bool = False,
    **kwargs,
) -> bool:
    """
    Check if the specified ``repo_name`` exists in the given ``parent_dir`` and
    is a valid git repository, otherwise clones it.
    Signature is the same as :func:`git_clone` except for ``force`` argument.

    :param force: skip user prompt and clone anyways if missing.
    :return: True if repo was missing and therefore cloned, False otherwise.
    :raise CommandAborted: if not ``force`` and the user cancelled the prompt.
    """
    if not title:
        title = repo_name_to_title(repo_name)
    if not is_git_repo(os.path.join(parent_dir, repo_name)):
        if not force:
            _logger.warning(f"Missing repo files for {title}" + (f" (@{branch})" if branch else ""))
            if not _logger.confirm("Do you want to download them now?"):
                raise CommandAborted()
        git_clone(parent_dir, repo_name, branch=branch, title=title, **kwargs)
        return True
    return False


@dataclass(frozen=True)
class GitWorktree:
    """Frozen dataclass representing a git worktree"""

    repo: Repo
    """The git repository"""

    path: str
    """The path of the worktree"""

    branch: str
    """The branch of the worktree"""

    commit: str
    """The commit of the worktree"""

    bare: bool = False
    """Whether the worktree is bare"""

    detached: bool = False
    """Whether the worktree is detached"""

    locked: Union[bool, str] = False
    """Whether the worktree is locked"""

    prunable: Union[bool, str] = False
    """Whether the worktree is prunable"""


def git_worktrees(repo: Repo) -> Dict[str, GitWorktree]:
    """
    Parse the list of worktrees for the given repository.

    :param repo: the git repository
    :return: a dict of worktrees, indexed by their path
    """
    worktrees: Dict[str, GitWorktree] = {}
    # worktree entries should start with "worktree" and will end with a blank line
    for worktree_entry in repo.git.worktree("list", "--porcelain").split("\n\n"):
        if not worktree_entry.strip().startswith("worktree"):
            _logger.warning(f"Bad git worktree entry for repo {repo.working_dir}: {worktree_entry}")
            continue

        values = {}
        for line in worktree_entry.strip().splitlines():
            # worktree attribute lines will always at least contain a label, optionally a space and the value
            label, *rest = line.strip().split(" ", 1)
            labels_fields_map = {
                "worktree": "path",
                "HEAD": "commit",
                **{n: n for n in ("branch", "bare", "detached", "locked", "prunable")},
            }
            field = labels_fields_map.get(label)
            if field is None:
                _logger.warning(
                    f"Unknown git worktree attribute '{label}' for repo {repo.working_dir}: {worktree_entry}"
                )
                continue
            values[field] = rest and rest[0] or True

        worktree = GitWorktree(repo=repo, **values)  # type: ignore
        worktrees[worktree.path] = worktree

    return worktrees


def git_worktree_create(
    parent_dir: str,
    repo_name: str,
    branch: Optional[str] = None,
    title: Optional[str] = None,
    force: bool = False,
    main_branch: Optional[str] = None,
    main_parent: Optional[str] = None,
    **kwargs,
) -> bool:
    """
    Creates a worktree clone of a repository.
    First ensures the ``main_branch`` is cloned, then creates a worktree of the repo
    at the specified ``branch``.
    Signature is the same as :func:`git_clone_if_missing` except for ``main_branch``
    and ``main_parent`` arguments.

    :param main_branch: the name of the main branch for the repo, defaults to ``master``.
    :param main_parent: the parent directory where the main clone will be stored.
        If not specified, defaults to ``parent_dir``'s parent directory / ``main_branch``.
    :return: True if the repo was cloned, False otherwise.
    """
    if main_branch is None:
        main_branch = "master"

    if not main_parent:
        # default to `parent_dir/../main_branch`, supposing it's odev repos dir
        main_parent = os.path.join(os.path.dirname(parent_dir), main_branch)

    did_clone = git_clone_if_missing(main_parent, repo_name, branch=main_branch, title=title, force=force, **kwargs)

    repo = Repo(os.path.join(main_parent, repo_name))
    worktree_branch = os.path.join(parent_dir, repo_name)
    if any(w.prunable for w in git_worktrees(repo).values()):
        repo.git.worktree("prune")
    try:
        repo.git.worktree("add", worktree_branch, branch)
    except GitCommandError:
        worktree_realpath = os.path.abspath(os.path.realpath(worktree_branch))
        if worktree_realpath not in git_worktrees(repo):
            raise

    return did_clone


def handle_git_error(e, log_level="ERROR") -> int:
    message = re.sub(r"((\n\s{0,}|\')(stderr|error):|\.?\'$)", "", e.stderr).strip()
    _logger.log(getLevelName(log_level), f"Git error, {message}")
    # return code
    return e.status


def get_remote(repo: Repo) -> Remote:
    """
    Get origin or the first defined remote for the given repository.

    :param repo: the repository for which to get the remote.
    :raise MissingRemote: if the repository doesn't have any remote
    :return: origin or the first defined remote.
    """
    try:
        return repo.remotes.origin
    except AttributeError:
        try:
            return repo.remotes[0]
        except IndexError:
            raise MissingRemote(f"Repository at {repo.working_tree_dir} has no remotes")


def git_pull(
    repo_path: str,
    branch: Optional[str] = None,
    title: Optional[str] = None,
    skip_prompt: bool = False,
    verbose: bool = True,
    confirm_message_t: Optional[str] = None,
) -> bool:
    """
    Pulls latest modifications from remote for a cloned git repository.

    :param repo_path: the path of the repo.
    :param branch: if specified, checks that the repo is at the given branch.
    :param title: an optional alternative name to display in the logger for the repo.
    :param verbose: whether to log messages as ``info`` rather than ``debug``.
    :param confirm_message_t: an alternative confirm message template than the default one.
    :return: True if the repo was updated, else False.
    """
    if not title:
        title = repo_name_to_title(repo_path)
    if not confirm_message_t:
        confirm_message_t = (
            "Local clone of {title} is {pending_commits} commits "
            "behind {tracking_branch}, do you want to update it now?"
        )

    log_level: int = getLevelName("INFO" if verbose else "DEBUG")
    _logger.log(
        log_level,
        f"Checking for updates in {title}" + (f" on branch {branch}" if branch else ""),
    )
    repo: Repo = Repo(repo_path)
    repo_remote: Remote = get_remote(repo)
    dotgit_path: str = os.path.abspath(getattr(repo, "_common_dir", None) or repo.git_dir)

    if dotgit_path not in _just_fetched_repos:
        try:
            repo_remote.fetch()
        except GitCommandError as e:
            if handle_git_error(e, log_level="WARNING") == 128:
                return False
            else:
                raise
        _just_fetched_repos.add(dotgit_path)

    head_branch = repo.head.ref
    if branch and head_branch.name != branch:
        # TODO: prompt user to checkout branch?
        raise HeadRefMismatch(f"HEAD is on {head_branch.name}, expected on {branch}")

    tracking_branch = head_branch.tracking_branch()
    if not tracking_branch:
        raise MissingTrackingBranch(f"No tracking branch for {head_branch.name}")

    pending_commits: int = tracking_branch.commit.count() - head_branch.commit.count()

    confirm_message: str = confirm_message_t.format(
        title=title,
        head_branch=head_branch.name,
        tracking_branch=tracking_branch.name,
        pending_commits=pending_commits,
    )
    if pending_commits > 0 and (skip_prompt or _logger.confirm(confirm_message)):
        _logger.log(log_level, f"Pulling {pending_commits} commits")
        repo.git.merge(tracking_branch.name, "--ff-only")
        _logger.success(f"Updated {title}!")
        return True

    return False


def git_clone_or_pull(
    parent_dir: str,
    repo_name: str,
    branch: Optional[str] = None,
    title: Optional[str] = None,
    skip_prompt: bool = False,
    conditional_clone_fn: Callable[..., bool] = git_clone_if_missing,  # FIXME: Protocol
    **kwargs,
) -> bool:
    """
    Check if the specified ``repo_name`` exists in the given ``parent_dir``,
    otherwise clones it, and pulls remote changes to bring up-to-date.
    Signature is the same as :func:`git_clone_if_missing` except for ``conditional_clone_fn``.

    :param conditional_clone_fn: the callable that conditionally clones the repo, returning
        True if cloned, False otherwise.
    :return: True if cloned or pulled (ie. user confirmed), else False
    """
    did_clone: bool = conditional_clone_fn(parent_dir, repo_name, branch=branch, title=title, **kwargs)

    if not did_clone:
        return git_pull(os.path.join(parent_dir, repo_name), branch=branch, title=title, skip_prompt=skip_prompt)

    return did_clone


def worktree_clone_or_pull(
    *args,
    main_branch: Optional[str] = None,
    main_parent: Optional[str] = None,
    **kwargs,
) -> bool:
    """
    Call :func:`git_clone_or_pull` with worktree cloning using :func:`git_worktree_create`.
    Signature is the same as :func:`git_clone_or_pull` except for ``conditional_clone_fn``
    that's already provided, and ``main_branch`` / ``main_parent`` which are
    the same from :func:`git_worktree_create`.
    """
    conditional_clone_fn = partial(git_worktree_create, main_branch=main_branch, main_parent=main_parent)
    return git_clone_or_pull(*args, conditional_clone_fn=conditional_clone_fn, **kwargs)  # type: ignore


def self_update() -> bool:
    """
    Check for updates in the odev repository and download them if necessary.

    :return: True if updates were pulled, False otherwise
    """
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        return False

    config = ConfigManager("odev")
    odev_path = config.get("paths", "odev")

    default_date = (datetime.today() - timedelta(days=1)).strftime(DEFAULT_DATETIME_FORMAT)
    update_check_interval = config.get("update", "check_interval") or 1
    last_update_check = config.get("update", "last_check") or default_date
    last_check_diff = (datetime.today() - datetime.strptime(last_update_check, DEFAULT_DATETIME_FORMAT)).days

    if last_check_diff < update_check_interval:
        return False

    try:
        did_update: bool = git_pull(
            odev_path,
            "odev",
            verbose=False,
            confirm_message_t=("An update is available for odev, do you want to download it now?"),
        )
    except (MissingTrackingBranch, HeadRefMismatch) as exc:
        _logger.debug(f"{exc}, odev running in development mode")
        return False

    if did_update:
        _logger.info("Checking for new odev package requirements")
        install_packages(requirements_dir=odev_path)

    config.set("update", "last_check", datetime.today().strftime(DEFAULT_DATETIME_FORMAT))

    return did_update


def get_worktree_list(odoo_path: str, repos: Union[str, List[str]]) -> List[str]:
    if isinstance(repos, str):
        repos = [repos]

    repos = [os.path.join(odoo_path, repo) for repo in repos if is_git_repo(os.path.join(odoo_path, repo))]

    re_worktree_versions = re.compile(r"\nbranch\srefs/heads/((?!master)[^\n]+)")
    all_versions: Set[str] = set()
    installed_versions: Set[str] = set()

    for repo_path in repos:
        repo = git.Repo(repo_path)
        _logger.debug(f"Launching git prune on {repo_path}")
        repo.git.worktree("prune")
        worktree_list = repo.git.worktree("list", "--porcelain")
        worktree_versions = set(re_worktree_versions.findall(worktree_list))
        all_versions |= worktree_versions
        installed_versions = all_versions & worktree_versions

    return list(installed_versions)


class GitCommitContext(ContextManager["GitCommitContext"]):
    def __init__(
        self, repo: Union[str, Repo], message: Optional[str] = None, stash: bool = True, ignore_empty: bool = True
    ):
        if isinstance(repo, str):
            repo = Repo(repo)
        assert isinstance(repo, Repo)

        self.repo: Repo = repo
        self.message: Optional[str] = message
        self._stash: bool = stash
        self._ignore_empty: bool = ignore_empty

        self._paths_to_commit: Set[str] = set()

    def __enter__(self) -> "GitCommitContext":
        if self._stash:
            _logger.debug("Stashing non-submodule related changes")
            stash_msg: str = self.repo.git.stash("push")
            if "No local changes to save".lower() in stash_msg.lower():
                self._stash = False

        return self

    def add(self, *paths: str) -> None:
        self._paths_to_commit.update(paths)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if any((exc_type, exc_val, exc_tb)):
            return

        if not self._paths_to_commit:
            _logger.debug("No paths set to commit, skipping")
            return

        if not self.message:
            raise ValueError("Did not specify a commit message")

        for path in self._paths_to_commit:
            self.repo.git.add(path)
        self._paths_to_commit.clear()

        try:
            self.repo.git.commit("-m", self.message)
        except CommandError as exc:
            if self._ignore_empty and "nothing added to commit" in str(exc):
                _logger.debug("Nothing to commit for changes in local repo")
            else:
                raise

        if self._stash:
            _logger.debug("Un-stashing previous non-submodule related changes")
            self.repo.git.stash("pop")
