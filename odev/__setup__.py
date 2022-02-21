import os
import shlex
import stat
import subprocess
from signal import SIGINT, SIGTERM, signal
from subprocess import DEVNULL, CalledProcessError
from types import FrameType
from typing import List, Optional, Tuple

from odev.utils import logging
from odev.utils.config import ConfigManager
from odev.utils.os import mkdir


_logger = logging.getLogger(__name__)


def signal_handler(signum: int, frame: Optional[FrameType]):
    print()  # Empty newline to make sure we're not writing next to a running prompt
    _logger.warning(f"Received signal ({signum}), aborting setup...")
    exit(signum)


def sudo_exec(command: str, password: Optional[str]):
    try:
        command = " ".join(
            [
                "echo",
                shlex.quote(password or ""),
                *("|", "sudo", "-S", "-k", "-s"),
                command,
            ]
        )
        subprocess.run(command, shell=True, check=True, stderr=DEVNULL, stdout=DEVNULL)
    except (PermissionError, CalledProcessError):
        raise PermissionError("Incorrect password, permission denied")


def run():
    """
    Setup wizard for odev
    """

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    # User input is needed for locations in which data is stored
    # We use a list of tuples to create missing directories
    # based on the answer to questions asked to the user
    # Tuple format: ('key_in_config', 'Question string?', 'default value')
    ASK_DIRS: List[Tuple[str, str, str]] = [
        ("odoo", "Where do you want to store Odoo's repositories on your machine?", "~/odoo/versions"),
        ("dump", "Where do you want to store Odoo databases' dump files?", "~/odoo/dumps"),
        ("dev", "Where do you want to store your Odoo custom developments repositories?", "~/odoo/dev"),
    ]

    try:
        cwd = os.getcwd()
        main = os.path.join(cwd, "main.py")

        suffix = "bin/odev"
        if _logger.confirm("Would you like to create a system-wide symlink to odev? [/usr/local/bin]"):
            _logger.info("Creating system-wide symlink for odev, this might require additional permissions")
            prefix = "/usr/local/"
        else:
            prefix = os.path.expanduser("~/.local/")
        ubin = os.path.join(prefix, suffix)

        rm_command = shlex.join(["rm", "-f", ubin])
        ln_command = shlex.join(["ln", "-s", main, ubin])
        password = None

        def get_password():
            return _logger.password("Password:")

        try:
            subprocess.run(rm_command, shell=True, check=True, stderr=DEVNULL)
        except (PermissionError, CalledProcessError):
            password = get_password()
            sudo_exec(rm_command, password)

        try:
            subprocess.run(ln_command, shell=True, check=True, stderr=DEVNULL)
        except (PermissionError, CalledProcessError):
            password = password or get_password()
            sudo_exec(ln_command, password)

        os.chmod(main, os.stat(main).st_mode | stat.S_IEXEC)

        ConfigManager("databases")

        with ConfigManager("odev") as odev_config:
            odev_config.set("paths", "odev", cwd)

            for key, question, default in ASK_DIRS:
                answer = _logger.ask(question, odev_config.get("paths", key, default))
                assert isinstance(answer, str)
                path = os.path.expanduser(answer)
                odev_config.set("paths", key, path)
                mkdir(path)

        _logger.success("All set, enjoy!")

    except Exception as exception:
        _logger.error(exception)
        exit(1)
