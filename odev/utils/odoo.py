import ast
import glob
import os
import re
import subprocess
from datetime import datetime, timedelta
from subprocess import DEVNULL
from typing import Any, List, Mapping, Optional

import requests
from packaging.version import Version

from odev.constants import (
    DEFAULT_DATETIME_FORMAT,
    ODOO_MANIFEST_NAMES,
    ODOO_MASTER_REPO,
    ODOO_REPOSITORIES,
    ODOO_UPGRADE_REPOSITORIES,
    PRE_11_SAAS_TO_MAJOR_VERSIONS,
    RE_ODOO_DBNAME,
)
from odev.exceptions import InvalidOdooDatabase, InvalidVersion
from odev.utils import logging
from odev.utils.config import ConfigManager
from odev.utils.github import get_worktree_list, git_clone_or_pull, worktree_clone_or_pull
from odev.utils.os import mkdir
from odev.utils.python import install_packages
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


def is_really_module(path: str, name: str) -> bool:
    return any(os.path.isfile(os.path.join(path, name, mname)) for mname in ODOO_MANIFEST_NAMES)


def get_manifest(path: str, module: str) -> Optional[Mapping[str, Any]]:
    """
    Get the content of the manifest of an Odoo module
    and parse its content to a usable dict.
    """
    for manifest_name in ODOO_MANIFEST_NAMES:
        manifest_path = os.path.join(path, module, manifest_name)

        if not os.path.isfile(manifest_path):
            continue

        with open(manifest_path) as manifest:
            return ast.literal_eval(manifest.read())

    return {}


def is_addon_path(path):
    def clean(name):
        name = os.path.basename(name)
        return name

    return any(clean(name) for name in os.listdir(path) if is_really_module(path, name))


def is_saas_db(url):
    session = requests.Session()
    url = url + "/" if not url.endswith("/") else url

    resp = session.get(url + "saas_worker/noop", allow_redirects=False)

    return resp.status_code == 200


def check_database_name(name: str) -> None:
    """
    Raise if the provided database name is not valid for Odoo.
    """
    if not RE_ODOO_DBNAME.match(name):
        raise InvalidOdooDatabase(
            f"`{name}` is not a valid odoo database name. "
            f"Only alphanumerical characters, underscore, hyphen and dot are allowed."
        )


def get_odoo_version(version: str) -> str:
    """
    Converts a loose version string into a valid Odoo version
    """

    def v_match(v):
        return re.match(r"(?:saas[-~+])?(\d+)\.(?:saas[-~+])?(\d+)", v)

    match = v_match(version)
    if not match and "saas" in version:
        minor_match = re.search(r"[~-](\d+)", version)
        if minor_match:
            major_version = PRE_11_SAAS_TO_MAJOR_VERSIONS.get(int(minor_match.group(1)))
            if major_version is not None:
                match = v_match(f"{major_version}.{version}")
    if not match:
        raise InvalidVersion(version)

    joined_version = ".".join(match.groups())
    parsed_version = Version(joined_version)
    if "saas" not in version and (parsed_version.minor == 0 or joined_version == "6.1"):
        return joined_version
    else:
        if parsed_version.major <= 10:
            return f"{parsed_version.major}.saas~{parsed_version.minor}"
        else:
            return f"saas~{parsed_version.major}.{parsed_version.minor}"


def parse_odoo_version(version: str) -> Version:
    """
    Parses an odoo version string into a `Version` object that can be compared.
    """
    try:
        return Version(re.sub("saas~", "", get_odoo_version(version)))
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
    python_version = odoo_python_versions.get(odoo_version_major)

    if python_version is not None:
        return python_version
    elif odoo_version_major < 11:
        return "2.7"
    else:
        raise NotImplementedError(f"No matching python version for odoo {odoo_version}")


def branch_from_version(version: str) -> str:
    if "saas" in version:
        parsed_version: Version = parse_odoo_version(version)
        if parsed_version.major <= 10:
            return f"saas-{parsed_version.minor}"
        else:
            return "".join(version.partition("saas")[1:]).replace("saas~", "saas-")
    return version


def version_from_branch(version: str) -> str:
    if version == "master":
        return version
    return get_odoo_version(version)


def repos_version_path(repos_path: str, version: str) -> str:
    branch: str = branch_from_version(version)
    version_path: str = os.path.join(repos_path, branch)
    return version_path


def prepare_odoobin(
    repos_path: str,
    version: str,
    venv_name: Optional[str] = None,
    venv: bool = True,
    upgrade: bool = False,
    skip_prompt: bool = False,
) -> None:
    """
    Prepares the environment for running odoo-bin.
    - Ensures all the needed repositories are cloned and up-to-date
    - Prepare the correct virtual environment (unless ``venv`` is explicitly set False)
    """
    venv_name = venv_name or "venv"
    branch: str = branch_from_version(version)
    available_version = get_worktree_list(repos_path + ODOO_MASTER_REPO, ODOO_REPOSITORIES)

    need_pull, last_update = _need_pull(version)

    do_pull = (
        skip_prompt
        or branch not in available_version
        or (
            need_pull
            and _logger.confirm(
                f"The last pull check for Odoo {version} was on " f"{last_update} do you want to pull now?"
            )
        )
    )

    ConfigManager("pull_check").set("version", version, datetime.today().strftime(DEFAULT_DATETIME_FORMAT))

    version_path: str = repos_version_path(repos_path, version)
    mkdir(version_path, 0o777)

    if venv or venv_name != "venv":
        prepare_venv(repos_path, version, venv_name)

    if not do_pull:
        return

    for pull_repo in ODOO_REPOSITORIES:
        do_pull |= worktree_clone_or_pull(version_path, pull_repo, branch, skip_prompt=do_pull)

    if upgrade:
        for pull_repo in ODOO_UPGRADE_REPOSITORIES:
            do_pull |= git_clone_or_pull(repos_path, pull_repo, skip_prompt=do_pull)


def prepare_venv(repos_path: str, version: str, venv_name: str):
    version_path: str = repos_version_path(repos_path, version)

    if not os.path.isdir(os.path.join(version_path, venv_name)):
        py_version = get_python_version(version)

        try:
            command = f'cd "{version_path}" && virtualenv --python={py_version} {venv_name}'
            _logger.info(f"Creating virtual environment: Odoo {version} + Python {py_version} ({venv_name})")
            with capture_signals():
                subprocess.run(command, shell=True, check=True, stdout=DEVNULL)

        except Exception:  # FIXME: W0703 broad-except
            # TODO: log Exception details (if any) or capture stdout+stderr to log?
            _logger.error(f"Error creating virtual environment for Python {py_version}")
            _logger.error(
                "Please check the correct version of Python is installed on your computer:\n"
                "\tsudo add-apt-repository ppa:deadsnakes/ppa\n"
                "\tsudo apt update\n"
                f"\tsudo apt install -y python{py_version} python{py_version}-dev"
            )


def prepare_requirements(repos_path: str, version: str, venv_name="venv", addons: Optional[List[str]] = None):
    version_path: str = repos_version_path(repos_path, version)

    venv_python: str = f"{version_path}/{venv_name}/bin/python"

    _logger.info(f"Checking for missing dependencies for {version} in requirements.txt")
    install_packages(packages="pip setuptools pudb ipdb websocket-client", python_bin=venv_python)

    all_addons = [os.path.join(version_path, "odoo")] + list_submodule_addons(addons or [])

    for addon_path in all_addons:
        try:
            install_packages(requirements_dir=addon_path, python_bin=venv_python)
        except FileNotFoundError:
            continue

    if parse_odoo_version(version).major < 10:
        # fix broken psycopg2 requirement for obsolete C lib bindings
        install_packages(packages="psycopg2==2.7.3.1", python_bin=venv_python)
        # use lessc v3 for odoo < 10
        subprocess.run("npm install less@3.0.4 less-plugin-clean-css", cwd=version_path, shell=True)


def _need_pull(version: str):
    limit = ConfigManager("odev").get("pull_check", "max_days") or 1
    default_date = (datetime.today() - timedelta(days=8)).strftime(DEFAULT_DATETIME_FORMAT)
    last_update = ConfigManager("pull_check").get("version", version) or default_date

    need_pull = (datetime.today() - datetime.strptime(last_update, DEFAULT_DATETIME_FORMAT)).days > int(limit)

    return need_pull, last_update


def list_submodule_addons(paths: List[str]) -> List[str]:
    submodule_addons: List[str] = []

    for addon in paths:
        submodule_addons += [
            path
            for path in glob.iglob(os.path.join(addon, "**/**"), recursive=True)
            if os.path.isdir(path) and is_addon_path(path)
        ]

    return list({os.path.normpath(path) for path in paths + submodule_addons})
