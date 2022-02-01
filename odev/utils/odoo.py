# -*- coding: utf-8 -*-

import os
import re
import subprocess
from datetime import datetime, timedelta
from subprocess import DEVNULL
from typing import List, Optional, Mapping

import requests
from packaging.version import Version

from odev.constants import RE_ODOO_DBNAME, ODOO_MANIFEST_NAMES, ODOO_MASTER_REPO
from odev.exceptions import InvalidOdooDatabase, InvalidVersion
from odev.utils.config import ConfigManager
from odev.utils.logging import getLogger
from odev.utils.os import mkdir
from odev.utils.github import git_clone_or_pull, worktree_clone_or_pull, get_worktree_list
from odev.utils.python import install_packages
from odev.utils.signal import capture_signals


logger = getLogger(__name__)

DEFAULT_DATETIME_FORMAT="%Y-%m-%d %H:%M:%S"

def is_addon_path(path):
    def clean(name):
        name = os.path.basename(name)
        return name

    def is_really_module(name):
        for mname in ODOO_MANIFEST_NAMES:
            if os.path.isfile(os.path.join(path, name, mname)):
                return True

    return any(clean(name) for name in os.listdir(path) if is_really_module(name))


def is_saas_db(url):
    session = requests.Session()
    url = url + "/" if not url.endswith("/") else url

    resp = session.get(url + "saas_worker/noop")

    return resp.status_code == 200


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


def parse_odoo_version(version: str) -> Version:
    """
    Parses an odoo version string into a `Version` object that can be compared.
    """
    try:
        return Version(re.sub(f"saas~", "", get_odoo_version(version)))
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
    odoo_version_major: int = parse_odoo_version(odoo_version).major
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

def version_from_branch(version: str) -> str:
    if "saas" in version:
        return "".join(version.partition("saas")[1:]).replace("saas-", "saas~")
    return version


def repos_version_path(repos_path: str, version: str) -> str:
    branch: str = branch_from_version(version)
    version_path: str = os.path.join(repos_path, branch)
    return version_path


def prepare_odoobin(
    repos_path: str,
    version: str,
    venv: bool = True,
    upgrade: bool = False,
    skip_prompt: bool = False,
) -> None:
    """
    Prepares the environment for running odoo-bin.
    - Ensures all the needed repositories are cloned and up-to-date
    - Prepare the correct virtual environment (unless ``venv`` is explicitly set False)
    """
    branch: str = branch_from_version(version)
    available_version = get_worktree_list(repos_path + ODOO_MASTER_REPO)

    need_pull , last_update = _need_pull(version)

    do_pull = skip_prompt or branch not in available_version or (
                need_pull and logger.confirm(
                    f"The last pull check for Odoo {version} was on "
                    f"{last_update} do you want to pull now?"
                )
            )

    ConfigManager("pull_check").set("version",version, datetime.today().strftime(DEFAULT_DATETIME_FORMAT))

    if not do_pull:
        return

    version_path: str = repos_version_path(repos_path, version)
    mkdir(version_path, 0o777)


    for pull_repo in ("odoo", "enterprise", "design-themes"):
        do_pull |= worktree_clone_or_pull(version_path, pull_repo, branch, skip_prompt=do_pull)

    if upgrade:
        for pull_repo in ("upgrade", "upgrade-specific", "upgrade-platform"):
            do_pull |= git_clone_or_pull(repos_path, pull_repo, skip_prompt=do_pull)

    if venv:
        prepare_venv(repos_path, version)



def prepare_venv(repos_path: str, version: str):
    version_path: str = repos_version_path(repos_path, version)

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


def prepare_requirements(repos_path: str, version: str, addons: Optional[List[str]] = None):
    if addons is None:
        addons = []

    version_path: str = repos_version_path(repos_path, version)

    venv_python: str = f"{version_path}/venv/bin/python"

    logger.info(f"Checking for missing dependencies for {version} in requirements.txt")
    for addon_path in addons + [os.path.join(version_path, "odoo")]:
        try:
            install_packages(requirements_dir=addon_path, python_bin=venv_python)
        except FileNotFoundError:
            continue

    install_packages(packages="pudb ipdb", python_bin=venv_python)

def _need_pull(version: int):
    limit = ConfigManager("odev").get("pull_check", "max_days") or 1
    default_date = (datetime.today() - timedelta(days=8)).strftime(DEFAULT_DATETIME_FORMAT)
    last_update = ConfigManager("pull_check").get('version', version) or default_date

    need_pull = (datetime.today() - datetime.strptime(last_update, DEFAULT_DATETIME_FORMAT)).days > int(limit)

    return need_pull, last_update
