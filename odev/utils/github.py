from typing import Optional

from git import Repo, GitCommandError
from github import Github
import os

from odev.utils import logging
from odev.utils.credentials import CredentialsHelper
from odev.utils.config import ConfigManager

logger = logging.getLogger(__name__)


def get_github(token: Optional[str] = None) -> Github:
    with CredentialsHelper() as creds:
        token = creds.secret("github.token", "Github token:", token)
        github: Github = Github(token)
        _ = github.get_user().login  # will raise with bad credentials
        return github


def git_clone(title, odoodir, name, branch):
    '''
    Clones a repository from GitHub.
    '''

    logger.info(f'Downloading {title}')
    Repo.clone_from(
        f'git@github.com:odoo/{name}.git',
        f'{odoodir}/{name}',
        multi_options=[f'--branch {branch}'],
    )


def git_worktree_create(title, odoodir, name, branch):
    config = ConfigManager('odev')
    odev_path = config.get('paths', 'odoo')
    worktree_base = os.path.join(odev_path, 'master')
    repo_path = os.path.join(worktree_base, name)

    if not os.path.isdir(repo_path):
        logger.info(f"The {title} master worktree directory is missing ! Downloading it now ;-)")
        logger.warning('This may take a while, please be patient...')
        git_clone(title, worktree_base, name, 'master')

    repo = Repo(repo_path)

    try:
        repo.git.worktree("add", f"{odoodir}/{name}", branch)
    except GitCommandError as g:
        repo.git.worktree("prune")
        repo.git.worktree("add", f"{odoodir}/{name}", branch)


def git_pull(title, odoodir, name, branch):
    '''
    Pulls modifications from a GitHub repository.
    '''

    logger.info(f'Checking for updates in {title} on branch {branch}')
    repo = Repo(f'{odoodir}/{name}')
    head = repo.head.ref
    tracking = head.tracking_branch()
    pending = len(
        list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}'))
    )

    if pending > 0:
        logger.warning(
            f'You are {logging.term.lightcoral_bold(str(pending))} commits behind '
            f'{tracking}, consider pulling the lastest changes'
        )

        if logger.confirm('Do you want to pull those commits now?'):
            logger.info(f'Pulling {pending} commits')
            _get_remote(repo).pull()
            logger.success('Up to date!')


def self_update() -> bool:
    '''
    Check for updates in the odev repository and download them if necessary.

    :return: True if updates were pulled, False otherwise
    '''

    config = ConfigManager('odev')
    odev_path = config.get('paths', 'odev')
    logger.debug(f'Fetching changes in remote repository of {odev_path}')
    repo = Repo(odev_path)
    _get_remote(repo).fetch()
    head = repo.head.ref
    tracking = head.tracking_branch()

    if not tracking:
        logger.debug('No remote branch set, running in development mode')
        return False

    pending = len(
        list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}'))
    )

    if pending > 0 and logger.confirm(
        'An update is available for odev, do you want to download it now?'
    ):
        logger.debug(f'Pulling updates: {head.path}..{tracking.path}')
        _get_remote(repo).pull()
        logger.success('Up to date!')
        return True

    return False


def _get_remote(repo):
    try:
        remote = repo.remotes.origin
    except AttributeError:
        remote = repo.remotes[0]
    return remote
