"""Generic utilities"""

import os
import pkgutil
import re
import subprocess
from getpass import getpass
from importlib import import_module
from types import ModuleType
from typing import MutableMapping, Any, Optional, Iterable, Tuple, Protocol, List, Dict

from clint.textui import puts, colored
from git import Repo


__all__ = [
    "quotes",
    "re_blanks",
    "re_extras",
    "re_psql",
    "sanitize",
    "require",
    "log",
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


quotes = {
    'info': colored.blue('[i]', False, True),
    'success': colored.green('[*]', False, True),
    'warning': colored.yellow('[!]', False, True),
    'error': colored.red('[-]', False, True),
    'debug': colored.black('[#]', False, True),
    'question': colored.magenta('[?]', False, True),
}

re_blanks = re.compile(r'([-\s]+)')
re_extras = re.compile(r'([^a-z0-9-_\s])')
re_psql = re.compile(r'^(pg_|[0-9])')


def sanitize(name: str):
    """
    Sanitizes the name of a database so that it can be used without creating
    any conflict in PostgreSQL due to improper formatting or forbidden
    characters.
    """

    require('name', name)

    name = str(name).lower()
    name = re_extras.sub('', name)
    name = re_blanks.sub('_', name)

    if re_psql.search(name):
        raise ValueError(name)

    return name


def require(name: str, value: str):
    """
    Makes sure a value is set, otherwise raise an exception.
    """

    if not value:
        raise Exception("Value \'%s\' is required; none given" % (name))


def log(level: str, text: str):
    """
    Prints a log message to the console.
    """

    puts('%s %s' % (quotes[level], text))


def confirm(question: str):
    """
    Asks the user to enter Y or N (case-insensitive).
    """
    answer = ''

    while answer not in ['y', 'n']:
        answer = input('%s %s [y/n] ' % (quotes['question'], question))[0].lower()

    return answer == 'y'


def ask(question: str, default=False):
    """
    Asks something to the user.
    """

    if default:
        return input('%s %s [%s] ' % (quotes['question'], question, default)) or default
    return input('%s %s ' % (quotes['question'], question))


def password(question: str):
    """
    Asks for a password.
    """

    return getpass(prompt='%s %s ' % (quotes['question'], question))


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

    log('info', 'Downloading %s on branch %s' % (title, branch))
    Repo.clone_from('git@github.com:odoo/%s.git' % (name), '%s/%s' % (odoodir, name), multi_options=['--branch %s' % (branch), '--single-branch'])


def git_pull(title, odoodir, name, branch):
    """
    Pulls modifications from a GitHub repository.
    """

    log('info', 'Checking for updates in %s on branch %s' % (title, branch))
    repo = Repo('%s/%s' % (odoodir, name))
    head = repo.head.ref
    tracking = head.tracking_branch()
    pending = len(list(tracking.commit.iter_items(repo, f'{head.path}..{tracking.path}')))

    if pending > 0:
        log('warning', 'You are %s commits behind %s, consider pulling the lastest changes' % (colored.red(pending), tracking))

        if confirm('Do you want to pull those commits now?'):
            log('info', 'Pulling %s commits' % (pending))
            repo.remotes.origin.pull()
            log('success', 'Up to date!')


def pre_run(odoodir, odoobin, version):
    """
    Prepares the environment for running odoo-bin.
    - Fetch last changes from GitHub
    - Prepare the correct virtual environment
    """

    if not os.path.isfile(odoobin):
        log('warning', 'Missing files for Odoo version %s' % (version))

        if not confirm('Do you want to download them now?'):
            log('info', 'Action canceled')
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
            log('info', 'Creating virtual environment: Odoo %s + Python %s ' % (version, python_version))
            subprocess.run(command, shell=True, check=True)
        except Exception:
            log('error', 'Error creating virtual environment for Python %s' % (python_version))
            log('error', 'Please check the correct version of Python is installed on your computer:\n    sudo add-apt-repository ppa:deadsnakes/ppa\n    sudo apt install -y python%s python%s-dev' % (python_version, python_version))

    command = '%s/venv/bin/python -m pip install -r %s/odoo/requirements.txt > /dev/null' % (odoodir, odoodir)
    log('info', 'Checking for missing dependencies in requirements.txt')
    subprocess.run(command, shell=True, check=True)


def curl(url, *args, with_headers=True, follow_redirects=True, silent=True):
    options = ["-k"]
    if with_headers:
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
