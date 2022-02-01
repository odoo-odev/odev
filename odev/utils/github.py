import git
import os
import os.path
import re
from functools import partial
from logging import getLevelName
from typing import Optional, Callable

from git import (
    Repo,
    GitCommandError,
    InvalidGitRepositoryError,
    NoSuchPathError,
    Head,
    RemoteReference,
    Remote,
)
from github import Github

from odev.exceptions import (
    CommandAborted,
    MissingTrackingBranch,
    HeadRefMismatch,
    MissingRemote,
)
from odev.utils import logging
from odev.utils.config import ConfigManager
from odev.utils.credentials import CredentialsHelper
from odev.utils.python import install_packages

logger = logging.getLogger(__name__)


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

    logger.info(
        f"Cloning {title or repo_name}" + (f" on branch {branch}" if branch else "")
    )
    Repo.clone_from(
        f"git@github.com:{url_path}.git",
        f"{parent_dir}/{repo_name}",
        multi_options=[f"--branch {branch}"] if branch else None,
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
            logger.warning(
                f"Missing repo files for {title}" + (f" (@{branch})" if branch else "")
            )
            if not logger.confirm("Do you want to download them now?"):
                raise CommandAborted()
        git_clone(parent_dir, repo_name, branch=branch, title=title, **kwargs)
        return True
    return False


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

    did_clone = git_clone_if_missing(
        main_parent, repo_name, branch=main_branch, title=title, force=force, **kwargs
    )

    repo = Repo(os.path.join(main_parent, repo_name))
    worktree_branch = os.path.join(parent_dir, repo_name)
    if "prunable gitdir" in repo.git.worktree("list", "--porcelain"):
        repo.git.worktree("prune")
    try:
        repo.git.worktree("add", worktree_branch, branch)
    except GitCommandError:
        worktree_realpath = os.path.abspath(os.path.realpath(worktree_branch))
        if worktree_realpath not in repo.git.worktree("list"):
            raise

    return did_clone

def handle_git_error(e, log_level="ERROR") -> int:
    message = re.sub(r'((\n\s{0,}|\')(stderr|error):|\.?\'$)', '', e.stderr).strip()
    logger.log(getLevelName(log_level), f'Git error, {message}')
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
    logger.log(
        log_level,
        f"Checking for updates in {title}" + (f" on branch {branch}" if branch else ""),
    )
    repo: Repo = Repo(repo_path)
    repo_remote: Remote = get_remote(repo)
    try:
        repo_remote.fetch()
    except GitCommandError as e:
        if handle_git_error(e, log_level="WARNING") == 128:
            return False
        else:
            raise
            
    head_branch: Head = repo.head.ref
    if branch and head_branch.name != branch:
        # TODO: prompt user to checkout branch?
        raise HeadRefMismatch(f"HEAD is on {head_branch.name}, expected on {branch}")

    tracking_branch: RemoteReference = head_branch.tracking_branch()
    if not tracking_branch:
        raise MissingTrackingBranch(f"No tracking branch for {head_branch.name}")

    pending_commits: int = tracking_branch.commit.count() - head_branch.commit.count()

    confirm_message: str = confirm_message_t.format(
        title=title,
        head_branch=head_branch.name,
        tracking_branch=tracking_branch.name,
        pending_commits=pending_commits,
    )
    if pending_commits > 0 and (skip_prompt or logger.confirm(confirm_message)):
        logger.log(log_level, f"Pulling {pending_commits} commits")
        repo_remote.pull()
        logger.success(f"Updated {title}!")
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
    otherwise clones it, and pulls remote changes to bring uptodate.
    Signature is the same as :func:`git_clone_if_missing` except for ``conditional_clone_fn``.

    :param conditional_clone_fn: the callable that conditionally clones the repo, returning
        True if cloned, False otherwise.
    :return: True if cloned or pulled (ie. user confirmed), else False
    """
    did_clone: bool = conditional_clone_fn(
        parent_dir, repo_name, branch=branch, title=title, skip_prompt=skip_prompt, **kwargs
    )

    if not did_clone:
        return git_pull(
            os.path.join(parent_dir, repo_name), branch=branch, title=title, skip_prompt=skip_prompt
        )

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
    conditional_clone_fn = partial(
        git_worktree_create, main_branch=main_branch, main_parent=main_parent
    )
    return git_clone_or_pull(*args, conditional_clone_fn=conditional_clone_fn, **kwargs)


def self_update() -> bool:
    """
    Check for updates in the odev repository and download them if necessary.

    :return: True if updates were pulled, False otherwise
    """
    config = ConfigManager("odev")
    odev_path = config.get("paths", "odev")
    try:
        did_update: bool = git_pull(
            odev_path,
            "odev",
            verbose=False,
            confirm_message_t=(
                "An update is available for odev, do you want to download it now?"
            ),
        )
    except (MissingTrackingBranch, HeadRefMismatch) as exc:
        logger.debug(f"{exc}, odev running in development mode")
        return False

    if did_update:
        logger.info(f'Checking for new odev package requirements')
        install_packages(requirements_dir=odev_path)

    return did_update

def get_worktree_list(odoo_path):
    worktree_list = git.Repo(odoo_path ).git.worktree('list', '--porcelain')
    odoo_version = [os.path.basename(b) for b in worktree_list.split("\n") if "branch" in b and "master" not in b]

    return odoo_version
