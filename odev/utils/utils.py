"""Generic utilities"""
import logging
import os
import pkgutil
import re
import subprocess
from getpass import getpass
from importlib import import_module
from types import ModuleType
from typing import MutableMapping, Any, Optional, Iterable, Tuple, Protocol, List, Dict, Union, Sequence

from git import Repo

from ..logging import term


__all__ = [
    "re_blanks",
    "re_extras",
    "re_dbname",
    "dbname_validate",
    "require",
    "format_question",
    "confirm",
    "ask",
    "password",
    "mkdir",
    "get_python_version",
    "git_clone",
    "git_pull",
    "pre_run",
    "curl",
    "ImportHook",
    "import_submodules"
]


_logger = logging.getLogger(__name__)


re_blanks = re.compile(r'([\s]+)')
re_extras = re.compile(r'([^a-z0-9-_\s])')
re_dbname = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]+$')


def dbname_validate(name: str):
    """
    Raise if the provided database name is not valid for odoo.
    """
    if not (re_dbname.match(name)):
        raise ValueError(
            f'"{name}" is not a valid odoo database name. '
            f'Only alphanumerical characters, underscore, hyphen and dot are allowed.'
        )


def require(name: str, value: str):
    """
    Makes sure a value is set, otherwise raise an exception.
    """

    if not value:
        raise Exception("Value \'%s\' is required; none given" % (name))


def format_question(question: str, choices: Optional[Union[str, Sequence[str]]] = None, default: Optional[str] = None, trailing: str = " ", choices_sep: str = "/") -> str:
    text_parts: List[str] = [term.bright_magenta('[?]'), question]
    if isinstance(choices, (list, tuple)):
        choices = choices_sep.join(choices)
    if choices:
        text_parts.append(f"[{choices}]")
    if default:
        text_parts.append(f"({default})")
    return " ".join(text_parts) + trailing


def confirm(question: str) -> bool:
    """
    Asks the user to enter Y or N (case-insensitive).
    """
    choices = ["y", "n"]
    answer: str = ""
    while answer not in choices:
        answer = input(format_question(question, choices=choices))[0].lower()
    return answer == "y"


def ask(question: str, default: Optional[str] = None) -> str:
    """
    Asks something to the user.
    """
    answer: str = input(format_question(question, default=default))
    if default and not answer:
        return default
    return answer


def password(question: str):
    """
    Asks for a password.
    """
    return getpass(format_question(question))


def mkdir(path: str, perm: int = 0o777):
    """
    Creates a directory on the filesystem and sets its permissions.
    """

    os.makedirs(path, perm, exist_ok=True)
    os.chmod(path, perm)


def get_python_version(odoo_version):
    if odoo_version == '14.0':
        return '3.7'
    if odoo_version == '13.0':
        return '3.6'
    if odoo_version == '12.0':
        return '3.5'
    if odoo_version == '11.0':
        return '3.5'
    return '2.7'


def git_clone(title, odoodir, name, branch):
    """
    Clones a repository from GitHub.
    """

    _logger.info('Downloading %s on branch %s' % (title, branch))
    Repo.clone_from('git@github.com:odoo/%s.git' % (name), '%s/%s' % (odoodir, name), multi_options=['--branch %s' % (branch), '--single-branch'])


def git_pull(title, odoodir, name, branch):
    """
    Pulls modifications from a GitHub repository.
    """

    _logger.info('Checking for updates in %s on branch %s' % (title, branch))
    repo = Repo('%s/%s' % (odoodir, name))
    head = repo.head.ref
    tracking = head.tracking_branch()
    pending = len(list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}')))

    if pending > 0:
        _logger.warning('You are %s commits behind %s, consider pulling the lastest changes' % (term.bright_red(pending), tracking))

        if confirm('Do you want to pull those commits now?'):
            _logger.info('Pulling %s commits' % (pending))
            repo.remotes.origin.pull()
            _logger.success('Up to date!')


def pre_run(odoodir, odoobin, version):
    """
    Prepares the environment for running odoo-bin.
    - Fetch last changes from GitHub
    - Prepare the correct virtual environment
    """

    if not os.path.isfile(odoobin):
        _logger.warning('Missing files for Odoo version %s' % (version))

        if not confirm('Do you want to download them now?'):
            _logger.info('Action canceled')
            return 0

        mkdir(odoodir, 0o777)

        git_clone('Odoo Community', odoodir, 'odoo', version)
        git_clone('Odoo Enterprise', odoodir, 'enterprise', version)
        git_clone('Odoo Design Themes', odoodir, 'design-themes', version)

    else:
        git_pull('Odoo Community', odoodir, 'odoo', version)
        git_pull('Odoo Enterprise', odoodir, 'enterprise', version)
        git_pull('Odoo Design Themes', odoodir, 'design-themes', version)

    if not os.path.isdir('%s/venv' % (odoodir)):
        try:
            python_version = get_python_version(version)
            command = 'cd %s && virtualenv --python=%s venv > /dev/null' % (odoodir, python_version)
            _logger.info('Creating virtual environment: Odoo %s + Python %s ' % (version, python_version))
            subprocess.run(command, shell=True, check=True)
        except Exception:
            _logger.error('Error creating virtual environment for Python %s' % (python_version))
            _logger.error('Please check the correct version of Python is installed on your computer:\n    sudo add-apt-repository ppa:deadsnakes/ppa\n    sudo apt install -y python%s python%s-dev' % (python_version, python_version))

    command = '%s/venv/bin/python -m pip install -r %s/odoo/requirements.txt > /dev/null' % (odoodir, odoodir)
    _logger.info('Checking for missing dependencies in requirements.txt')
    subprocess.run(command, shell=True, check=True)


# TODO: move to requests library
def curl(url, *args, include_response_headers=True, follow_redirects=True, silent=True):
    options = ["-k"]
    if include_response_headers:
        options.append("-i")
    if follow_redirects:
        options.append("-L")
    if silent:
        options.append("-s")
    compiled_args = ' '.join(options + list(args))
    cmdline = f'''curl {compiled_args} "{url}"'''
    stream = os.popen(cmdline)
    return stream.read().strip()


class ImportHook(Protocol):
    """Typing protocol for import hook callables"""
    def __call__(self, module: ModuleType) -> Optional[Iterable[Tuple[str, Any]]]:
        ...


def import_submodules(
    base_path: str,
    globals_: MutableMapping[str, Any],
    package: Optional[str] = None,
    on_import: Optional[ImportHook] = None,
) -> List[str]:
    """
    Dynamically import all submodules (non-recursively) into the given dict.

    :param base_path: the base path where to look for submodules.
    :param globals_: a dict where the imported modules will be stored.
    :param package: optional package name required to enable relative imports.
    :param on_import: optional hook that will be called with the imported module
        as sole argument to do custom additional processing and can insert more
        attributes and values into the package namespace.
    :return: the list of imported module names.
    """
    imported_names: List[str] = []
    module_name: str
    for _, module_name, _ in pkgutil.iter_modules(base_path):  # type: ignore
        imported_module: ModuleType = import_module("." + module_name, package=package)
        added_attributes: Dict[str, Any] = {module_name: imported_module}
        if on_import is not None:
            hook_additions: Optional[Iterable[Tuple[str, Any]]]
            hook_additions = on_import(imported_module)
            if hook_additions is not None:
                added_attributes.update(hook_additions)
        for attr_name, attr_value in added_attributes.items():
            globals_[attr_name] = attr_value
            imported_names.append(attr_name)
    return imported_names
