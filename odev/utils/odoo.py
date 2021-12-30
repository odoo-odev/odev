# -*- coding: utf-8 -*-

import os
import subprocess
from subprocess import DEVNULL
from typing import List, Optional

from odev.constants import RE_ODOO_DBNAME, ODOO_MANIFEST_NAMES
from odev.exceptions import InvalidOdooDatabase
from odev.utils import logging
from odev.utils.os import mkdir
from odev.utils.github import git_clone_or_pull, worktree_clone_or_pull
from odev.utils.signal import capture_signals


logger = logging.getLogger(__name__)


def is_addon_path(path):
    def clean(name):
        name = os.path.basename(name)
        return name

    def is_really_module(name):
        for mname in ODOO_MANIFEST_NAMES:
            if os.path.isfile(os.path.join(path, name, mname)):
                return True

    return any(clean(name) for name in os.listdir(path) if is_really_module(name))


def check_database_name(name: str) -> None:
    '''
    Raise if the provided database name is not valid for Odoo.
    '''
    if not RE_ODOO_DBNAME.match(name):
        raise InvalidOdooDatabase(
            f'`{name}` is not a valid odoo database name. '
            f'Only alphanumerical characters, underscore, hyphen and dot are allowed.'
        )


def get_python_version(odoo_version):
    if '.' in odoo_version:
        odoo_version = odoo_version.split('.')[0]

    if odoo_version == '15':
        return '3.8'
    if odoo_version == '14':
        return '3.7'
    if odoo_version == '13':
        return '3.6'
    if odoo_version == '12':
        return '3.5'
    if odoo_version == '11':
        return '3.5'
    return '2.7'


def prepare_odoobin(
    repos_path: str,
    version: str,
    addons: Optional[List[str]] = None,
    venv: bool = True,
    upgrade: bool = False,
    force: bool = False,
) -> None:
    """
    Prepares the environment for running odoo-bin.
    - Ensures all the needed repositories are cloned and up-to-date
    - Prepare the correct virtual environment
    """
    version_path: str = os.path.join(repos_path, version)  # TODO: DRY, make global fn
    mkdir(version_path, 0o777)

    force |= worktree_clone_or_pull(version_path, "odoo", version, force=force)
    force |= worktree_clone_or_pull(version_path, "enterprise", version, force=force)
    force |= worktree_clone_or_pull(version_path, "design-themes", version, force=force)

    if upgrade:
        force |= git_clone_or_pull(repos_path, "upgrade", force=force)
        force |= git_clone_or_pull(repos_path, "upgrade-specific", force=force)
        force |= git_clone_or_pull(repos_path, "upgrade-platform", force=force)

    if venv:
        prepare_venv(repos_path, version, addons)


def prepare_venv(repos_path: str, version: str, addons: Optional[List[str]] = None):
    if addons is None:
        addons = []

    version_path: str = os.path.join(repos_path, version)  # TODO: DRY, make global fn

    if not os.path.isdir(os.path.join(version_path, "venv")):
        py_version = get_python_version(version)

        try:
            command = f'cd "{version_path}" && virtualenv --python={py_version} venv'
            logger.info(
                f"Creating virtual environment: Odoo {version} + Python {py_version}"
            )
            with capture_signals():
                subprocess.run(command, shell=True, check=True, stdout=DEVNULL)

        except Exception:  # FIXME: W0703 broad-except
            # TODO: log Exception details (if any) or capture stdout+stderr to log?
            logger.error(f"Error creating virtual environment for Python {py_version}")
            logger.error(
                "Please check the correct version of Python is installed on your computer:\n"
                "\tsudo add-apt-repository ppa:deadsnakes/ppa\n"
                f"\tsudo apt install -y python{py_version} python{py_version}-dev"
            )


def prepare_requirements(version_path: str, addons: List[str] = []):
    logger.info('Checking for missing dependencies in requirements.txt')

    for addon_path in addons + [os.path.join(version_path, "odoo")]:
        requirements_path: str = os.path.join(addon_path, "requirements.txt")
        if not os.path.exists(requirements_path):
            continue
        command = (
            f'"{version_path}/venv/bin/python" -m pip install -r "{requirements_path}"'
        )
        logger.debug(f"Installing requirements for {os.path.basename(addon_path)}")

        with capture_signals():
            subprocess.run(command, shell=True, check=True, stdout=DEVNULL)

    command = f'{version_path}/venv/bin/python -m pip install pudb ipdb > /dev/null'
    logger.debug(f'Installing developpment tools : {command}')

    with capture_signals():
        subprocess.run(command, shell=True, check=True)
