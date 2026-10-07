import os
import pty
import termios
from subprocess import CalledProcessError, CompletedProcess
from time import monotonic
from unittest.mock import patch

from odev.common import bash
from odev.common.console import console

from tests.fixtures import OdevTestCase


PRIVILEGED_COMMAND = "cat /etc/shadow"


class TestCommonBash(OdevTestCase):
    """Test the execution of system commands."""

    def test_01_valid_command(self):
        """A simple system call should work."""
        exec_result = bash.execute("echo 'Hello, odev!'")
        self.assertIsInstance(exec_result, CompletedProcess)
        self.assertEqual(exec_result.stdout, b"Hello, odev!\n")

    def test_02_invalid_command(self):
        """A command that fails should raise an exception."""
        with self.assertRaises(CalledProcessError):
            bash.execute("notacommand")

    def test_03_invalid_command_no_raise(self):
        """A command that fails should return None if raise_on_error is False."""
        exec_result = bash.execute("notacommand", raise_on_error=False)
        self.assertIsNone(exec_result)

    def test_04_detached(self):
        """A command that is run in detached mode should not block the program."""
        start = monotonic()
        bash.detached("sleep 1")
        self.assertLess(monotonic() - start, 1)


class TestCommonBashStream(OdevTestCase):
    """Streaming a command should yield every line of its output, however it is split between reads.

    Streaming only happens with a terminal on the standard input, which a test suite does not have: a
    pseudo-terminal stands in for it.
    """

    def setUp(self):
        super().setUp()
        master, slave = pty.openpty()
        stdin = os.fdopen(slave, "rb", buffering=0)
        self.addCleanup(os.close, master)
        self.addCleanup(stdin.close)
        self.terminal: int = slave

        patcher = patch.object(bash.sys, "stdin", stdin)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_01_lines_are_split_within_a_read(self):
        """Lines received together should be yielded one by one, without their line endings."""
        self.assertEqual(bash._split_lines(b"first\r\nsecond\r\n"), (["first", "second"], b""))

    def test_02_incomplete_line_is_kept(self):
        """The beginning of a line should be kept until its end is received."""
        lines, remainder = bash._split_lines(b"first\r\nlas")

        self.assertEqual(lines, ["first"])
        self.assertEqual(bash._split_lines(remainder + b"t\r\n"), (["last"], b""))

    def test_03_stream_yields_all_lines(self):
        """A command writing more than a read can hold should have all its lines yielded in order."""
        lines = list(bash.stream("seq 1 20000"))
        self.assertEqual(lines, [str(number) for number in range(1, 20001)])

    def test_04_stream_yields_unterminated_last_line(self):
        """Output that does not end with a line break should not be lost."""
        self.assertEqual(list(bash.stream("printf 'first\\nlast'")), ["first", "last"])

    def test_05_stream_survives_invalid_text(self):
        """Bytes that are not valid text should not cost the lines received along with them."""
        self.assertEqual(
            list(bash.stream("printf 'before\\n\\377\\376\\nafter\\n'")),
            ["before", "\ufffd\ufffd", "after"],
        )

    def test_06_stream_is_silent_when_abandoned(self):
        """A caller that stops reading a failing command should not have an error raised behind its back.

        An error raised while a generator is being closed never reaches the caller: the interpreter
        reports it as ignored, which is what is watched for here.
        """
        lines = bash.stream("seq 1 20000; echo Failed; exit 1")

        with patch.object(bash.sys, "unraisablehook") as unraisable:
            for line in lines:
                if line == "Failed":
                    break

            lines.close()

        unraisable.assert_not_called()

    def test_07_terminal_keeps_processing_output(self):
        """Only what is typed should be read raw: a line break still has to return to the start of the line."""
        original = termios.tcgetattr(self.terminal)
        lines = bash.stream("echo streaming")
        next(lines)
        _, output_flags, _, local_flags, *_ = termios.tcgetattr(self.terminal)

        self.assertTrue(output_flags & termios.OPOST and output_flags & termios.ONLCR)
        self.assertFalse(local_flags & (termios.ICANON | termios.ECHO))

        list(lines)

        self.assertEqual(termios.tcgetattr(self.terminal), original)

    def test_08_stream_raises_on_failure(self):
        """A streamed command that fails should raise once its output was consumed."""
        with self.assertRaises(CalledProcessError):
            list(bash.stream("echo failing; exit 3"))


class TestCommonBashSudo(OdevTestCase):
    """Elevation should be attempted once a command fails, and only with a password at hand.

    The subprocess and the effective user are both simulated: shelling out to `sudo` would make the result
    depend on the local sudoers policy, and asking for a real elevation from a test suite is not something
    a developer should have to accept. A machine granting passwordless sudo would run the privileged
    command for real, and running the suite as root skips elevation entirely.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_sudo_password)
        self.commands: list[str] = []

    def restore_sudo_password(self):
        """Clear the session password cached in the module by the sudo tests."""
        bash.sudo_password = None

    def failure(self, command: str) -> CalledProcessError:
        """Build the error raised by a command the user is not allowed to run."""
        return CalledProcessError(1, command, output=b"", stderr=b"Permission denied")

    def patch_subprocess(self, sudo_succeeds: bool = False):
        """Patch the subprocess call, recording commands and failing until sudo is used.

        :param sudo_succeeds: Whether the elevated command should succeed instead of failing again.
        """

        def run(command: str, **kwargs):
            self.commands.append(command)

            if sudo_succeeds and command.startswith("sudo "):
                return CompletedProcess(command, 0, stdout=b"elevated", stderr=b"")

            raise self.failure(command)

        return self.patch(bash, "run_subprocess", side_effect=run)

    def patch_unprivileged_user(self):
        """Pretend the suite runs as a regular user, so the elevation path is taken."""
        return self.patch(bash.os, "geteuid", return_value=1000)

    def test_01_password_is_asked_once_the_command_failed(self):
        """The session password should only be requested after a first, unprivileged attempt."""
        with (
            self.patch_subprocess(),
            self.patch_unprivileged_user(),
            self.patch(console, "secret", return_value="secret") as mock_secret,
            self.assertRaises(CalledProcessError),
        ):
            bash.execute(PRIVILEGED_COMMAND, sudo=True)

        mock_secret.assert_called_once()
        self.assertEqual(self.commands, [PRIVILEGED_COMMAND, f"sudo -Sks {PRIVILEGED_COMMAND}"])

    def test_02_no_password_does_not_elevate(self):
        """Without a password there is nothing to elevate with, and the original error should surface."""
        with (
            self.patch_subprocess(),
            self.patch_unprivileged_user(),
            self.patch(console, "secret", return_value=None),
            self.assertRaises(CalledProcessError),
        ):
            bash.execute(PRIVILEGED_COMMAND, sudo=True)

        self.assertEqual(self.commands, [PRIVILEGED_COMMAND])

    def test_03_no_password_no_raise(self):
        """A command failing without a password should return None when not raising."""
        with (
            self.patch_subprocess(),
            self.patch_unprivileged_user(),
            self.patch(console, "secret", return_value=None),
        ):
            exec_result = bash.execute(PRIVILEGED_COMMAND, sudo=True, raise_on_error=False)

        self.assertIsNone(exec_result)

    def test_04_cached_password_is_reused(self):
        """A password from an earlier command should be reused rather than asked again."""
        bash.sudo_password = "cached"  # noqa: S105

        with (
            self.patch_subprocess(sudo_succeeds=True),
            self.patch_unprivileged_user(),
            self.patch(console, "secret") as mock_secret,
        ):
            exec_result = bash.execute(PRIVILEGED_COMMAND, sudo=True)

        mock_secret.assert_not_called()

        if exec_result is None:
            self.fail("the elevated command should have returned a result")

        self.assertEqual(exec_result.stdout, b"elevated")

    def test_05_wrong_password_raises(self):
        """A password rejected by sudo should let the second failure surface."""
        bash.sudo_password = "wrongpassword"  # noqa: S105

        with self.patch_subprocess(), self.patch_unprivileged_user(), self.assertRaises(CalledProcessError):
            bash.execute(PRIVILEGED_COMMAND, sudo=True)

    def test_06_wrong_password_no_raise(self):
        """A password rejected by sudo should return None when not raising."""
        bash.sudo_password = "wrongpassword"  # noqa: S105

        with self.patch_subprocess(), self.patch_unprivileged_user():
            exec_result = bash.execute(PRIVILEGED_COMMAND, sudo=True, raise_on_error=False)

        self.assertIsNone(exec_result)

    def test_07_wrong_password_is_forgotten(self):
        """A rejected password should not be kept and asked again on the next command."""
        bash.sudo_password = "wrongpassword"  # noqa: S105

        with self.patch_subprocess(), self.patch_unprivileged_user():
            bash.execute(PRIVILEGED_COMMAND, sudo=True, raise_on_error=False)

        self.assertIsNone(bash.sudo_password)

    def test_08_root_does_not_elevate(self):
        """Running as root already has the privileges, sudo would add nothing."""
        with (
            self.patch_subprocess(),
            self.patch(bash.os, "geteuid", return_value=0),
            self.patch(console, "secret") as mock_secret,
        ):
            exec_result = bash.execute(PRIVILEGED_COMMAND, sudo=True, raise_on_error=False)

        self.assertIsNone(exec_result)
        mock_secret.assert_not_called()
        self.assertEqual(self.commands, [PRIVILEGED_COMMAND])
