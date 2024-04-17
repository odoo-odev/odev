from subprocess import CalledProcessError, CompletedProcess
from time import monotonic

from odev.common import bash
from odev.common.console import console

from tests.fixtures import OdevTestCase


class TestCommonBash(OdevTestCase):
    """Test the execution of system commands."""

    def test_01_valid_command(self):
        """A simple system call should work"""
        exec_result = bash.execute("echo 'Hello, odev!'")
        self.assertIsInstance(exec_result, CompletedProcess)
        self.assertEqual(exec_result.stdout, b"Hello, odev!\n")

    def test_02_invalid_command(self):
        """A command that fails should raise an exception"""
        with self.assertRaises(CalledProcessError):
            bash.execute("notacommand")

    def test_03_invalid_command_no_raise(self):
        """A command that fails should return None if raise_on_error is False"""
        exec_result = bash.execute("notacommand", raise_on_error=False)
        self.assertIsNone(exec_result)

    def test_04_sudo_no_password(self):
        """A command that fails should be re-executed with sudo and fail if the password is not set"""
        with self.assertRaises(CalledProcessError), self.patch(console, "secret") as mock_secret:
            mock_secret.return_value = None
            bash.execute("cat /etc/shadow", sudo=True)

    def test_05_sudo_no_password_no_raise(self):
        """A command that fails should be re-executed with sudo and return None if the password is not set
        and raise_on_error is False
        """
        with self.patch(console, "secret", None):
            exec_result = bash.execute("cat /etc/shadow", sudo=True, raise_on_error=False)
        self.assertIsNone(exec_result)

    def test_06_sudo_wrong_password(self):
        """A command that fails should be re-executed with sudo and fail again if the password is wrong"""
        bash.sudo_password = "wrongpassword"

        with self.assertRaises(CalledProcessError):
            bash.execute("cat >> /etc/shadow", sudo=True)

    def test_07_sudo_wrong_password_no_raise(self):
        """A command that fails should be re-executed with sudo and return None if the password is wrong
        and raise_on_error is False
        """
        bash.sudo_password = "wrongpassword"
        exec_result = bash.execute("cat >> /etc/shadow", sudo=True, raise_on_error=False)
        self.assertIsNone(exec_result)

    def test_08_detached(self):
        """A command that is run in detached mode should not block the program"""
        start = monotonic()
        bash.detached("sleep 1")
        self.assertLess(monotonic() - start, 1)
