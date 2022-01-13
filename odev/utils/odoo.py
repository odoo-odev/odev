# -*- coding: utf-8 -*-

import os
import subprocess
from typing import List

from odev.constants import RE_ODOO_DBNAME, ODOO_MANIFEST_NAMES
from odev.exceptions import InvalidOdooDatabase
from odev.utils import logging
from odev.utils.os import mkdir
from odev.utils.github import git_pull, git_clone, git_worktree_create
from odev.utils.signal import capture_signals
from odev.exceptions import CommandAborted


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


def pre_run(odoodir: str, odoobin: str, version: str, upgrade: bool = False, addons: List[str] = []):
    '''
    Prepares the environment for running odoo-bin.
    - Fetch last changes from GitHub
    - Prepare the correct virtual environment
    '''

    if not os.path.isfile(odoobin):
        logger.warning('Missing files for Odoo version %s' % (version))

        if not logger.confirm('Do you want to download them now?'):
            raise CommandAborted()

        mkdir(odoodir, 0o777)

        git_worktree_create('Odoo Community', odoodir, 'odoo', version)
        git_worktree_create('Odoo Enterprise', odoodir, 'enterprise', version)
        git_worktree_create('Odoo Design Themes', odoodir, 'design-themes', version)

    else:
        git_pull('Odoo Community', odoodir, 'odoo', version)
        git_pull('Odoo Enterprise', odoodir, 'enterprise', version)
        git_pull('Odoo Design Themes', odoodir, 'design-themes', version)

    if not os.path.isdir('%s/venv' % (odoodir)):
        python_version = get_python_version(version)

        try:
            command = 'cd %s && virtualenv --python=%s venv > /dev/null' % (odoodir, python_version)
            logger.info('Creating virtual environment: Odoo %s + Python %s ' % (version, python_version))

            with capture_signals():
                subprocess.run(command, shell=True, check=True)
        except Exception:
            logger.error('Error creating virtual environment for Python %s' % (python_version))
            logger.error(
                'Please check the correct version of Python is installed on your computer:\n'
                '\tsudo add-apt-repository ppa:deadsnakes/ppa\n'
                '\tsudo apt install -y python%s python%s-dev'
                % (python_version, python_version)
            )

    if upgrade:
        odoodir_parent = os.path.normpath(os.path.join(odoodir, '..'))
        odoodir_upgrade = os.path.normpath(os.path.join(odoodir_parent, 'upgrade'))

        if not os.path.isdir(odoodir_upgrade):
            logger.warning('Missing files for Odoo Upgrade')

            if not logger.confirm('Do you want to download them now?'):
                raise CommandAborted()

            git_clone('Odoo Upgrade', odoodir_parent, 'upgrade', 'master')
        else:
            git_pull('Odoo Upgrade', odoodir_parent, 'upgrade', 'master')

def prepare_requirements(odoodir: str, addons: List[str] = []):
    logger.info('Checking for missing dependencies in requirements.txt')

    def requirements_path(path):
        return os.path.join(path, 'requirements.txt')

    for addon in filter(lambda a: os.path.exists(requirements_path(a)), addons + [os.path.join(odoodir, 'odoo')]):
        command = f'{odoodir}/venv/bin/python -m pip install -r {requirements_path(addon)} > /dev/null'
        logger.debug(f'Installing requirements.txt: {command}')

        with capture_signals():
            subprocess.run(command, shell=True, check=True)

    command = f'{odoodir}/venv/bin/python -m pip install pudb ipdb > /dev/null'
    logger.debug(f'Installing developpment tools : {command}')

    with capture_signals():
        subprocess.run(command, shell=True, check=True)
