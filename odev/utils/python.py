"""Python and venv-related utilities"""

import os
import subprocess
import sys
from subprocess import DEVNULL
from typing import Iterable, Optional, Union

from odev.utils import logging
from odev.utils.signal import capture_signals


_logger = logging.getLogger(__name__)


def install_packages(
    requirements_dir: Optional[str] = None,
    packages: Union[str, Iterable[str], None] = None,
    python_bin: Optional[str] = None,
    log_level: int = logging.logging.DEBUG,
) -> None:
    """
    Installs packages using pip in a python environment.

    :param requirements_dir: the base path where to look for ``requirements.txt``.
        This parameter is mutually exclusive with ``packages``.
    :param packages: a string or iterable of strings of package specs to install.
        This parameter is mutually exclusive with ``requirements_dir``.
    :param python_bin: the python interpreter to use to run pip (eg. a venv python).
        If omitted, defaults to the current odev interpreter (`sys.executable`).
    :param log_level: the logging level to use for messages. Defaults to `logging.DEBUG`.
    :raise FileNotFoundError: if no ``requirements.txt`` is found.
    """
    if bool(requirements_dir) == bool(packages):
        raise AttributeError('Must specify either "base_path" or "packages"')
    if python_bin is None:
        python_bin = sys.executable

    pip_args: str
    log_msg: str
    if requirements_dir:
        requirements_path: str = os.path.join(requirements_dir, "requirements.txt")
        if not os.path.exists(requirements_path):
            raise FileNotFoundError(f"No requirements.txt in {requirements_dir}")
        pip_args = f'-r "{requirements_path}"'
        log_msg = f"Installing requirements in {os.path.basename(requirements_dir)}"
    else:
        assert packages
        if not isinstance(packages, str):
            packages = " ".join(packages)
        pip_args = packages
        log_msg = f"Installing python packages: {packages}"

    command: str = f'"{python_bin}" -m pip install {pip_args}'
    _logger.log(log_level, log_msg)

    with capture_signals():
        subprocess.run(command, shell=True, check=True, stdout=DEVNULL)
