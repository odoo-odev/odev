"""Utilities for working with the operating system and issue BASH-like commands to
the subsystem.
"""

import os
import pty
import select
import signal
import sys
import termios
import tty
from collections.abc import Generator
from subprocess import (
    DEVNULL,
    CalledProcessError,
    CompletedProcess,
    Popen,
    run as run_subprocess,
)
from time import monotonic

from odev.common.console import console
from odev.common.logging import logging


__all__ = ["detached", "execute", "stream"]


logger = logging.getLogger(__name__)

CTRL_C, CTRL_D = b"\x03", b"\x04"

STREAM_CHUNK_SIZE = 65536
"""Maximum number of bytes read at once from the output of a streamed process."""

STREAM_DRAIN_TIMEOUT = 1.0
"""Seconds given to read what a streamed process left unread when it exited."""

global sudo_password  # noqa: PLW0604
sudo_password: str | None = None


# --- Helpers ------------------------------------------------------------------


def __run_command(
    command: str,
    capture: bool = True,
    sudo_password: str | None = None,
    env: dict[str, str] | None = None,
    input_data: bytes | None = None,
) -> CompletedProcess[bytes]:
    """Execute a command as a subprocess.
    If `sudo_password` is provided and not `None`, the command will be executed with
    elevated privileges.

    :param str command: The command to execute.
    :param bool capture: Whether to capture the output of the command.
    :param str sudo_password: The password to use when executing the command with
        elevated privileges.
    :param dict env: The environment variables to use when executing the command.
    :return: The result of the command execution.
    :rtype: CompletedProcess
    """
    if sudo_password is not None:
        command = f"sudo -Sks {command}"
        sudo_password = f"{sudo_password}\n"

    return run_subprocess(  # noqa: S602 - intentional use of shell=True
        command,
        shell=True,
        check=True,
        capture_output=capture,
        input=input_data or (sudo_password.encode() if sudo_password is not None else None),
        env=env,
    )


def __raise_or_log(exception: CalledProcessError, do_raise: bool) -> None:
    """Raise or log an exception.

    :param CalledProcessError exception: The exception to raise or log.
    :param bool do_raise: Whether to raise the exception or log it.
    """
    if stdout := exception.stdout.decode().strip():
        logger.debug(stdout)

    if stderr := exception.stderr.decode().strip():
        logger.error(stderr)

    if do_raise:
        raise exception


# --- Public API ---------------------------------------------------------------


def execute(
    command: str,
    sudo: bool = False,
    raise_on_error: bool = True,
    env: dict[str, str] | None = None,
    input_data: str | bytes | None = None,
) -> CompletedProcess[bytes] | None:
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
        logger.debug(f"Running process: {command}")
        if isinstance(input_data, str):
            input_data = input_data.encode()
        process_result = __run_command(command, env=env, input_data=input_data)
    except CalledProcessError as exception:
        # If already running as root, sudo will not work
        if not sudo or not os.geteuid():
            __raise_or_log(exception, raise_on_error)
            return None

        global sudo_password  # noqa: PLW0603
        sudo_password = sudo_password or console.secret("Session password:")

        if not sudo_password:
            __raise_or_log(exception, raise_on_error)
            return None

        try:
            process_result = __run_command(command, sudo_password=sudo_password, env=env)
        except CalledProcessError as exception:
            sudo_password = None
            __raise_or_log(exception, raise_on_error)
            return None

    return process_result


def run(command: str, env: dict[str, str] | None = None, input_data: str | bytes | None = None) -> CompletedProcess:
    """Execute a command in the operating system and wait for it to complete.
    Output of the command will not be captured and will be printed to the console
    in real-time.

    :param str command: The command to execute.
    :param dict env: The environment variables to use when executing the command.
    :param input_data: The data to pass to the command as stdin.
    """
    logger.debug(f"Running process: {command}")
    if isinstance(input_data, str):
        input_data = input_data.encode()
    return __run_command(command, capture=False, env=env, input_data=input_data)


def detached(command: str) -> Popen[bytes]:
    """Execute a command in the operating system and detach it from the current process.

    :param str command: The command to execute.
    """
    logger.debug(f"Running detached process: {command}")
    return Popen(command, shell=True, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)  # noqa: S602 - intentional use of shell=True


def _stream_no_tty(
    command: str, env: dict[str, str] | None = None, input_data: str | bytes | None = None
) -> Generator[str, None, None]:
    """Execute a command in non-interactive mode and yield its output."""
    logger.warning("STDIN is not a TTY, running command in non-interactive mode")
    exec_process = execute(command, env=env, input_data=input_data)

    if not exec_process:
        yield ""
        return

    yield from exec_process.stdout.decode().splitlines()


def _set_raw_input(terminal: int) -> None:
    """Put a terminal in raw mode for what is typed in it, leaving what is written to it alone.

    Raw mode hands over every key as it is pressed, which is what lets CTRL+C and CTRL+D be passed on to
    a streamed process. It also stops the terminal from returning to the start of the line on a line
    break, leaving the cursor below the end of the last line written: that part is turned back on.

    :param terminal: The file descriptor of the terminal.
    """
    tty.setraw(terminal)
    attributes = termios.tcgetattr(terminal)
    attributes[1] |= termios.OPOST | termios.ONLCR
    termios.tcsetattr(terminal, termios.TCSANOW, attributes)


def _split_lines(received: bytes) -> tuple[list[str], bytes]:
    """Split the output received from a streamed process into the lines it completes.

    :param received: The output received so far and not yet yielded.
    :return: The complete lines, and the beginning of a line whose end was not received yet.
    :rtype: tuple[list[str], bytes]
    """
    *lines, remainder = received.split(b"\n")

    return [_decode_line(line) for line in lines], remainder


def _decode_line(line: bytes) -> str:
    """Decode a line of output from a streamed process.

    :param line: The line as it was received, without its line break.
    :return: The text of the line, bytes that are not valid text being replaced rather than failing the
        lines received along with them.
    :rtype: str
    """
    return line.decode(errors="replace").rstrip("\r")


def _read_lines(master: int, pending: bytearray) -> Generator[str, None, None]:
    """Read what a streamed process has written so far and yield the lines it completes.

    Reading one byte at a time costs a system call per character of output, which is what an Odoo server
    logging thousands of lines ends up waiting on.

    :param master: The file descriptor to read the output of the process from.
    :param pending: The beginning of a line whose end was not received yet, updated in place.
    :yield: Each line completed by what was read, without its line break.
    """
    received = os.read(master, STREAM_CHUNK_SIZE)

    if b"\n" not in received:
        # Nothing to split yet, and splitting again what is pending on every read of a very long line
        # would cost more with each of them.
        pending += received
        return

    lines, remainder = _split_lines(bytes(pending) + received)
    pending[:] = remainder

    yield from lines


def stream(
    command: str, env: dict[str, str] | None = None, input_data: str | bytes | None = None
) -> Generator[str, None, None]:
    """Execute a command in the operating system and stream its output line by line.
    :param str command: The command to execute.
    :param dict env: The environment variables to use when executing the command.
    :param input_data: The data to pass to the command as stdin.
    """
    logger.debug(f"Streaming process: {command}")

    if not sys.stdin.isatty():
        yield from _stream_no_tty(command, env, input_data)
        return

    original_tty = termios.tcgetattr(sys.stdin)
    _set_raw_input(sys.stdin.fileno())
    master, slave = pty.openpty()

    process: Popen | None = None

    try:
        process = Popen(  # noqa: S602
            command,
            stdout=slave,
            stderr=slave,
            stdin=slave,
            start_new_session=True,
            shell=True,
            env=env,
        )

        if input_data:
            if isinstance(input_data, str):
                input_data = input_data.encode()
            os.write(master, input_data)

        pending = bytearray()

        while process.poll() is None:
            rlist, _, _ = select.select([sys.stdin, master], [], [], 0.1)

            # Input received on STDIN, pass it to the child process
            if sys.stdin in rlist:
                # Ignore characters other than CTRL+C or CTRL+D, allow requesting
                # the process to stop or exiting interactive debuggers
                char = os.read(sys.stdin.fileno(), 1)

                if char == CTRL_C:
                    # Kill the entire process group
                    os.killpg(process.pid, signal.SIGTERM)

                if char in (CTRL_C, CTRL_D):
                    os.write(master, char)
                    os.write(master, b"\n")

            # Output received from process, yield for further processing
            if master in rlist:
                yield from _read_lines(master, pending)

        # The process may exit between two reads, with its last lines still waiting to be read. A process
        # it left behind could keep writing forever though, and nothing reads the keyboard anymore.
        drain_deadline = monotonic() + STREAM_DRAIN_TIMEOUT

        while monotonic() < drain_deadline and select.select([master], [], [], 0)[0]:
            yield from _read_lines(master, pending)

        if pending:
            yield _decode_line(bytes(pending))

    finally:
        os.close(slave)
        os.close(master)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_tty)

    # Raised once the output was consumed, not while cleaning up: a caller that stops reading early is
    # closing the generator, and an error raised then is reported as ignored instead of reaching it.
    if process is not None and process.returncode:
        raise CalledProcessError(process.returncode, command)
