"""
Utilities for working with the operating system and issue BASH-like commands to
the subsystem.
"""

from os import geteuid
from shlex import quote
from subprocess import CalledProcessError, CompletedProcess, run
from typing import Optional

from odev.common import prompt
from odev.common.logging import logging


__all__ = ["execute"]


logger = logging.getLogger(__name__)


global sudo_password
sudo_password: Optional[str] = None


# --- Helpers ------------------------------------------------------------------


def __run_command(command: str) -> CompletedProcess[bytes]:
    """Execute a command as a subprocess."""
    return run(command, shell=True, check=True, capture_output=True)


def __raise_or_log(exception: CalledProcessError, do_raise: bool) -> None:
    """Raise or log an exception.

    :param CalledProcessError exception: The exception to raise or log.
    :param bool do_raise: Whether to raise the exception or log it.
    """
    if do_raise:
        raise exception

    logger.error(exception)


# --- Public API ---------------------------------------------------------------


def execute(command: str, sudo: bool = False, raise_on_error: bool = True) -> Optional[CompletedProcess]:
    """Execute a command in the operating system.

    If sudo is set and the command fails, the user will be prompted to enter his password
    and the command will be re-executed with elevated privileges.

    **Warning** If using this method with user input, use `shlex.quote` to prevent command injection.

    :param str command: The command to execute.
    :param bool sudo: Whether to execute the command with elevated privileges.
    :param bool raise_on_error: Whether to raise an exception if the command fails.
    :return: The result of the command execution, or None of an error was encountered.
    :rtype: CompletedProcess
    """
    try:
        logger.debug(f"Running process: {quote(command)}")
        process_result = __run_command(command)
    except CalledProcessError as exception:
        logger.debug(f"sudo: {sudo}, geteuid: {geteuid()}")

        # If already running as root, sudo will not work
        if not sudo or not geteuid():
            logger.debug(f"Process failed: {quote(command)}")
            return __raise_or_log(exception, raise_on_error)

        global sudo_password
        sudo_password = sudo_password or prompt.secret("Session password:")

        if sudo_password is None:
            return __raise_or_log(exception, raise_on_error)

        try:
            process_result = __run_command(f"echo {quote(sudo_password)} | sudo -Sks {command}")
        except CalledProcessError as exception:
            logger.debug(f"Process failed with elevated privileges: {quote(command)}")
            exception.cmd = exception.cmd.replace(quote(sudo_password), "*" * len(sudo_password))
            sudo_password = None
            return __raise_or_log(exception, raise_on_error)

    logger.debug(f"Completed process with return code {process_result.returncode}: {command}")
    return process_result
