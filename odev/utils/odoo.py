# -*- coding: utf-8 -*-

import os
import re
import subprocess
from subprocess import DEVNULL
from typing import List, Optional, Mapping

from distutils.version import StrictVersion

from odev.constants import RE_ODOO_DBNAME, ODOO_MANIFEST_NAMES
from odev.exceptions import InvalidOdooDatabase, InvalidVersion
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


def get_odoo_version(version: str) -> str:
    """
    Converts a loose version string into a valid Odoo version
    """
    match = re.match(r"(?:saas[-~+])?(\d+)\.(?:saas[-~+])?(\d+)", version)
    if not match:
        raise InvalidVersion(version)
    return (".saas~" if "saas" in version else ".").join(match.groups())


def parse_odoo_version(version: str) -> StrictVersion:
    """
    Parses an odoo version string into a `StrictVersion` object that can be compared.
    """
    try:
        return StrictVersion(re.sub(f"saas~", "", get_odoo_version(version)))
    except ValueError as exc:
        raise InvalidVersion(version) from exc


def get_python_version(odoo_version: str) -> str:
    """Get the correct python version for the given odoo version"""
    odoo_python_versions: Mapping[int, str] = {
        15: "3.8",
        14: "3.7",
        13: "3.6",
        12: "3.6",
        11: "3.5",
    }
    odoo_version_major: int = parse_odoo_version(odoo_version).version[0]
    python_version: str = odoo_python_versions.get(odoo_version_major)
    if python_version is not None:
        return python_version
    elif odoo_version_major < 11:
        return "2.7"
    else:
        raise NotImplementedError(f"No matching python version for odoo {odoo_version}")


def branch_from_version(version: str) -> str:
    if "saas" in version:
        return "".join(version.partition("saas")[1:]).replace("saas~", "saas-")
    return version


def repos_version_path(repos_path: str, version: str) -> str:
    branch: str = branch_from_version(version)
    version_path: str = os.path.join(repos_path, branch)
    return version_path


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
    branch: str = branch_from_version(version)

    version_path: str = repos_version_path(repos_path, version)
    mkdir(version_path, 0o777)

    force |= worktree_clone_or_pull(version_path, "odoo", branch, force=force)
    force |= worktree_clone_or_pull(version_path, "enterprise", branch, force=force)
    force |= worktree_clone_or_pull(version_path, "design-themes", branch, force=force)

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
