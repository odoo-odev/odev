from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import patch

import pytest

from odev.common import bash, prompt


class TestCommonBash:
    def test_execute_valid_command(self):
        """A simple system call should work"""
        exec_result = bash.execute("echo 'Hello, odev!'")
        assert isinstance(exec_result, CompletedProcess), "should return a CompletedProcess"
        assert exec_result.stdout == b"Hello, odev!\n", "should return the command output 'Hello, odev!'"

    def test_execute_invalid_command(self):
        """A command that fails should raise an exception"""
        with pytest.raises(CalledProcessError) as _:
            bash.execute("notacommand")

    def test_execute_invalid_command_no_raise(self):
        """A command that fails should return None if raise_on_error is False"""
        exec_result = bash.execute("notacommand", raise_on_error=False)
        assert exec_result is None, "should return None"

    def test_execute_sudo_no_password(self):
        """A command that fails should be re-executed with sudo and fail if the password is not set"""
        with pytest.raises(CalledProcessError) as _, patch.object(prompt, "secret") as mock_secret:
            mock_secret.return_value = None
            bash.execute("cat /etc/shadow", sudo=True)

    def test_execute_sudo_no_password_no_raise(self):
        """A command that fails should be re-executed with sudo and return None if the password is not set
        and raise_on_error is False
        """
        with patch.object(prompt, "secret") as mock_secret:
            mock_secret.return_value = None
            exec_result = bash.execute("cat /etc/shadow", sudo=True, raise_on_error=False)
        assert exec_result is None, "should return None"

    def test_execute_sudo_wrong_password(self):
        """A command that fails should be re-executed with sudo and fail again if the password is wrong"""
        bash.sudo_password = "wrongpassword"
        with pytest.raises(CalledProcessError) as _:
            bash.execute("cat /etc/shadow", sudo=True)

    def test_execute_sudo_wrong_password_no_raise(self):
        """A command that fails should be re-executed with sudo and return None if the password is not wrong
        and raise_on_error is False
        """
        bash.sudo_password = "wrongpassword"
        exec_result = bash.execute("cat /etc/shadow", sudo=True, raise_on_error=False)
        assert exec_result is None, "should return None"

    def test_detached(self):
        """A command that is run in detached mode should not block the program"""
        bash.detached("sleep 1")
        assert True, "should not block the program"
