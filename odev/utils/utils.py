"""Generic utilities"""
import logging
import math
import os
import pkgutil
import random
import re
import subprocess
import time
from collections import defaultdict
from contextlib import ExitStack
from getpass import getpass
from importlib import import_module
from types import ModuleType
from typing import (
    MutableMapping,
    Any,
    Optional,
    Iterable,
    Tuple,
    Protocol,
    List,
    Dict,
    Union,
    Sequence,
    Mapping,
)

import enlighten
from git import Repo

from ..log import term


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
    "import_submodules",
    "poll_loop",
    "SpinnerBar",
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


def poll_loop(poll_interval: float):
    while True:
        time.sleep(poll_interval)
        yield


class SpinnerBar:
    def __init__(self, message: Optional[str] = None):
        br_start: int = ord("\u2800")
        br_end: int = ord("\u28ff")
        self._density_bins: Mapping[int, List[str]] = defaultdict(list)
        for o in range(br_start, br_end):
            self._density_bins[bin(o - br_start).count("1")].append(chr(o))
        self._density_bins = dict(self._density_bins)
        self._db_max: int = max(self._density_bins.keys())
        self._message: Optional[str] = message
        self._manager: enlighten.Manager = enlighten.get_manager()
        self._status_bar: enlighten.StatusBar = self._manager.status_bar(
            "",
            color="white_on_deeppink4",
            justify=enlighten.Justify.CENTER,
            leave=False,
        )
        self._exit_stack: ExitStack = ExitStack()

    def __enter__(self):
        self._exit_stack.enter_context(self._manager)
        self._exit_stack.enter_context(self._status_bar)
        return self

    @property
    def message(self) -> Optional[str]:
        return self._message

    @message.setter
    def message(self, value: Optional[str]) -> None:
        self._message = value

    def update(self, pos: Optional[float] = None):
        padded_message: str = f" {self._message} " if self.message else ""
        bar_width: int = term.width - len(padded_message)
        if pos is None:
            pos = (-time.monotonic() * 40) / bar_width
        intensities: List[float] = [
            (
                0.5
                - 0.5
                * math.cos((max(0.0, min(-1 + 2 * pos + p, 1.0)) + 1) * 2 * math.pi)
            )
            * math.sin(p * math.pi) ** 0.5
            for i in range(bar_width)
            if (p := (i / bar_width)) is not None
        ]
        bar_str: str = "".join(
            random.choice(
                self._density_bins[
                    int((self._db_max + 0.99999) * max(0.0, min(i, 1.0)))
                ]
            )
            for i in intensities
        )
        status_str: str = padded_message + bar_str[::-1]
        self._status_bar.update(status_str)
        self._status_bar.refresh()

    def loop(self, poll_interval: float, spinner_fps: float = 20):
        spinner_interval: float = 1 / spinner_fps
        tick: float = time.monotonic()
        try:
            while True:
                time.sleep(spinner_interval)
                since_last_tick: float = time.monotonic() - tick
                duration: float = max(1.0, poll_interval / max(1, int(poll_interval / 2.5)))
                pos: float = (since_last_tick / duration) % 1.0
                self.update(pos=pos)
                if since_last_tick < poll_interval:
                    continue
                tick = time.monotonic()
                yield
        except StopIteration:
            return

    def __exit__(self, *exc_args):
        self._exit_stack.close()
        self._status_bar.__exit__(*exc_args)
        self._manager.__exit__(*exc_args)
