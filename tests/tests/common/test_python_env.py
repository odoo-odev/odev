from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import MagicMock, patch

from odev.common import bash
from odev.common.python import PythonEnv

from tests.fixtures import OdevTestCase


class TestPythonEnv(OdevTestCase):
    """Test the PythonEnv class."""

    @classmethod
    def setUpClass(cls):
        with patch("odev.common.odev.Odev.start", return_value=None):
            super().setUpClass()

    def test_run_script_streaming_success(self):
        """Test run_script with a streaming process that succeeds."""
        env = PythonEnv(path="/tmp/fake_venv", version="3.10")  # noqa: S108

        with (
            self.patch(Path, "exists", return_value=True),
            self.patch(PythonEnv, "exists", return_value=True),
            self.patch(PythonEnv, "python", Path("/tmp/fake_venv/bin/python")),  # noqa: S108
            self.patch(bash, "stream", return_value=iter(["line 1", "line 2"])),
        ):
            progress_mock = MagicMock()
            result = env.run_script("fake_script.py", stream=True, progress=progress_mock)

            self.assertIsInstance(result, CompletedProcess)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(progress_mock.call_count, 2)
            progress_mock.assert_any_call("line 1")
            progress_mock.assert_any_call("line 2")

    def test_run_script_streaming_failure(self):
        """Test run_script with a streaming process that fails."""
        env = PythonEnv(path="/tmp/fake_venv", version="3.10")  # noqa: S108

        def streaming_failure(command, **_kwargs):
            yield "line 1"
            raise CalledProcessError(1, command)

        with (
            self.patch(Path, "exists", return_value=True),
            self.patch(PythonEnv, "exists", return_value=True),
            self.patch(PythonEnv, "python", Path("/tmp/fake_venv/bin/python")),  # noqa: S108
            self.patch(bash, "stream", side_effect=streaming_failure),
        ):
            progress_mock = MagicMock()
            result = env.run_script("fake_script.py", stream=True, progress=progress_mock)

            self.assertIsInstance(result, CompletedProcess)
            self.assertEqual(result.returncode, 1)
            progress_mock.assert_called_once_with("line 1")
