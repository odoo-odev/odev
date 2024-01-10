"""
Utilities for working with the operating system and issue BASH-like commands to
the subsystem.
"""

from os import geteuid
from shlex import quote
from subprocess import (
    DEVNULL,
    PIPE,
    STDOUT,
    CalledProcessError,
    CompletedProcess,
    Popen,
    run as run_subprocess,
)
from typing import Generator, Optional

from odev.common.console import console
from odev.common.logging import logging


__all__ = ["execute", "detached", "stream"]


logger = logging.getLogger(__name__)


global sudo_password
sudo_password: Optional[str] = None


# --- Helpers ------------------------------------------------------------------


def __run_command(command: str, capture: bool = True, sudo_password: str = None) -> CompletedProcess[bytes]:
    """Execute a command as a subprocess.
    If `sudo_password` is provided and not `None`, the command will be executed with
    elevated privileges.

    :param str command: The command to execute.
    :param bool capture: Whether to capture the output of the command.
    :param str sudo_password: The password to use when executing the command with
        elevated privileges.
    :return: The result of the command execution.
    :rtype: CompletedProcess
    """

    if sudo_password is not None:
        command = f"sudo -Sks {command}"
        sudo_password = quote(f"{sudo_password}\n")

    return run_subprocess(
        command,
        shell=True,
        check=True,
        capture_output=capture,
        input=sudo_password.encode() if sudo_password is not None else None,
    )


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
    """Execute a command in the operating system and wait for it to complete.
    Output of the command will be captured and returned after the execution completes.

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
            __raise_or_log(exception, raise_on_error)
            return None

        global sudo_password
        sudo_password = sudo_password or console.secret("Session password:")

        if sudo_password is None:
            __raise_or_log(exception, raise_on_error)
            return None

        try:
            process_result = __run_command(command, sudo_password=sudo_password)
        except CalledProcessError as exception:
            logger.debug(f"Process failed with elevated privileges: {quote(command)}")
            sudo_password = None
            __raise_or_log(exception, raise_on_error)
            return None

    return process_result


def run(command: str) -> CompletedProcess:
    """Execute a command in the operating system and wait for it to complete.
    Output of the command will not be captured and will be printed to the console
    in real-time.

    :param str command: The command to execute.
    """
    logger.debug(f"Running process: {quote(command)}")
    return __run_command(command, capture=False)


def detached(command: str) -> Popen[bytes]:
    """Execute a command in the operating system and detach it from the current process.

    :param str command: The command to execute.
    """
    logger.debug(f"Running detached process: {quote(command)}")
    return Popen(command, shell=True, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)


def stream(command: str) -> Generator[str, None, None]:
    """Execute a command in the operating system and stream its output .

    :param str command: The command to execute.
    """
    logger.debug(f"Streaming process: {quote(command)}")
    process = Popen(command, shell=True, stdout=PIPE, stderr=STDOUT)

    for line in iter(process.stdout.readline, b""):
        yield line.rstrip().decode()
