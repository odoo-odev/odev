"""
Utilities for working with the operating system and issue BASH-like commands to
the subsystem.
"""

import os
import pty
import select
import sys
import termios
import tty
from shlex import quote
from subprocess import (
    DEVNULL,
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


def __run_command(command: str, capture: bool = True, sudo_password: Optional[str] = None) -> CompletedProcess[bytes]:
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


def execute(command: str, sudo: bool = False, raise_on_error: bool = True) -> Optional[CompletedProcess[bytes]]:
    """Execute a command in the operating system and wait for it to complete.
    Output of the command will be captured and returned after the execution completes.

    If sudo is set and the command fails, the user will be prompted to enter his password
    and the command will be re-executed with elevated privileges.

    **Warning** If using this method with user input, use `shlex.quote` to prevent command injection.

    :param str command: The command to execute.
    :param bool sudo: Whether to execute the command with elevated privileges.
    :param bool raise_on_error: Whether to raise an exception if the command fails.
    :return: The result of the command execution, or None if an error was encountered and `raise_on_error` is `False`.
    :rtype: Optional[CompletedProcess]
    """
    try:
        logger.debug(f"Running process: {quote(command)}")
        process_result = __run_command(command)
    except CalledProcessError as exception:

        # If already running as root, sudo will not work
        if not sudo or not os.geteuid():
            logger.debug(f"Process failed: {quote(command)}")
            __raise_or_log(exception, raise_on_error)
            return None

        global sudo_password
        sudo_password = sudo_password or console.secret("Session password:")

        if not sudo_password:
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
    """Execute a command in the operating system and stream its output line by line.
    :param str command: The command to execute.
    """
    logger.debug(f"Streaming process: {quote(command)}")
    original_tty = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno())
    master, slave = pty.openpty()

    try:
        process = Popen(
            command,
            shell=True,
            stdout=slave,
            stderr=slave,
            stdin=slave,
            start_new_session=True,
            universal_newlines=True,
        )

        received_buffer: bytes = b""

        while process.poll() is None:
            rlist, _, _ = select.select([sys.stdin, master], [], [], 0.1)

            # Input received on STDIN, pass it to the child process
            if sys.stdin in rlist:
                char = os.read(sys.stdin.fileno(), 1)

                # Ignore characters other than CTRL+C or CTRL+D, allow requesting
                # the process to stop
                if char in (b"\x03", b"\x04"):
                    os.write(master, char)

            # Output received from process, yield for further processing
            if master in rlist:
                received = os.read(master, 1)

                if not received:
                    continue

                if received != b"\n":
                    received_buffer += received
                    continue

                received_buffer = received_buffer.strip()
                yield received_buffer.decode()
                received_buffer = b""
                os.write(sys.stdout.fileno(), b"\r")

    finally:
        os.close(slave)
        os.close(master)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_tty)
