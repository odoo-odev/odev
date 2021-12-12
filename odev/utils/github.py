from typing import Optional

from git import Repo
from github import Github

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

    logger.info('Downloading %s on branch %s' % (title, branch))
    Repo.clone_from(
        f'git@github.com:odoo/{name}.git',
        f'{odoodir}/{name}',
        multi_options=[f'--branch {branch}', '--single-branch'],
    )


def git_pull(title, odoodir, name, branch):
    '''
    Pulls modifications from a GitHub repository.
    '''

    logger.info(f'Checking for updates in {title} on branch {branch}')
    repo = Repo(f'{odoodir}/{name}')
    head = repo.head.ref
    tracking = head.tracking_branch()
    pending = len(list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}')))

    if pending > 0:
        logger.warning(
            f'You are {logging.term.lightcoral_bold(str(pending))} commits behind '
            f'{tracking}, consider pulling the lastest changes'
        )

        if logger.confirm('Do you want to pull those commits now?'):
            logger.info(f'Pulling {pending} commits')
            repo.remotes.origin.pull()
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
    repo.remotes.origin.fetch()
    head = repo.head.ref
    tracking = head.tracking_branch()

    if not tracking:
        logger.debug('No remote branch set, running in development mode')
        return False

    pending = len(list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}')))

    if pending > 0 and logger.confirm('An update is available for odev, do you want to download it now?'):
        logger.debug(f'Pulling updates: {head.path}..{tracking.path}')
        repo.remotes.origin.pull()
        logger.success('Up to date!')
        return True

    return False
