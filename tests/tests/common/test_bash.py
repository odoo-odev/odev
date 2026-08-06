from subprocess import CalledProcessError, CompletedProcess
from time import monotonic

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
