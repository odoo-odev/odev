import os
import shlex
import subprocess
from abc import ABC
from datetime import datetime
from pathlib import Path

from odev._constants import DEFAULT_DATETIME_FORMAT, DEFAULT_VENV_NAME
from odev._utils import logging
from odev._utils.config import ConfigManager
from odev._utils.github import git_clone_or_pull
from odev._utils.odoo import _need_pull, prepare_venv
from odev._utils.os import mkdir
from odev._utils.python import install_packages
from odev._utils.signal import capture_signals
from odev.structures import commands


_logger = logging.getLogger(__name__)

_SUPPORT_TOOLS = "support-tools"
_DEFAULT_PATH = str(Path(Path.home(), "odoo", _SUPPORT_TOOLS))
_SELECT_DIR_QUESTION = f"Select dir for {_SUPPORT_TOOLS}"


class RunStandardMixin(commands.LocalDatabaseCommand, ABC):
    """
    Mixin to include run standard arguments
    """

    arguments = [
        {
            "aliases": ["--remove-studio"],
            "dest": "remove_studio",
            "action": "store_true",
            "help": "Remove studio customization (default False)",
        },
        {
            "aliases": ["--dry-run"],
            "dest": "dry_run",
            "action": "store_true",
            "help": "Print SQL queries but not commit",
        },
    ]


# structure
# + odoo
# | + support-tools (path)
#   | - support-tools (git repo)
#   | - venv (virtual environment)
def _get_support_tools_path():
    with ConfigManager("odev") as odev_config:
        path: str = odev_config.get("paths", _SUPPORT_TOOLS)
        if path is None:
            answer = _logger.ask(_SELECT_DIR_QUESTION, odev_config.get("paths", _SUPPORT_TOOLS, _DEFAULT_PATH))
            assert isinstance(answer, str)
            path = os.path.expanduser(answer)
            odev_config.set("paths", _SUPPORT_TOOLS, path)
            mkdir(path)
    return path


def _clone_or_pull(root_path):
    """
    Decorator to check last update before update
    """
    need_pull, last_update = _need_pull(_SUPPORT_TOOLS)
    if need_pull:
        git_clone_or_pull(root_path, _SUPPORT_TOOLS)
        ConfigManager("pull_check").set("version", _SUPPORT_TOOLS, datetime.today().strftime(DEFAULT_DATETIME_FORMAT))


def _prepare_command(python_exec, root_path, args):
    command_args = [
        python_exec,
        str(Path(root_path, _SUPPORT_TOOLS, "clean_database.py")),
    ]
    if args.remove_studio:
        command_args.append("--remove-studio")
    if args.dry_run:
        command_args.append("--dry-run")
    if args.log_level == "DEBUG":
        command_args.append("--verbose")
    command_args.append(args.database)
    command = shlex.join(command_args)
    return command


class RunStandard(RunStandardMixin):
    """
    Removes all trace of custom modules, allowing the database to run with just standard code
    """

    name = "run_standard"
    aliases = ["rd"]

    def run(self) -> int:
        root_path = _get_support_tools_path()

        _clone_or_pull(root_path)
        prepare_venv(root_path, "3.8")
        python_exec = str(Path(root_path, DEFAULT_VENV_NAME, "bin", "python"))
        install_packages(str(Path(root_path, _SUPPORT_TOOLS)), python_bin=python_exec)

        command = _prepare_command(python_exec, root_path, self.args)
        _logger.info(f"Running: {command}")

        with capture_signals():
            return subprocess.run(command, shell=True, check=True, capture_output=False).returncode
