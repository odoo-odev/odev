from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import MagicMock, patch

from odev.common import bash
from odev.common.errors import OdevError
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
            stream_filter_mock = MagicMock(side_effect=lambda x: x)
            result = env.run_script("fake_script.py", stream=True, stream_filter=stream_filter_mock)

            self.assertIsInstance(result, CompletedProcess)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(stream_filter_mock.call_count, 2)
            stream_filter_mock.assert_any_call("line 1")
            stream_filter_mock.assert_any_call("line 2")

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
            stream_filter_mock = MagicMock(side_effect=lambda x: x)
            result = env.run_script("fake_script.py", stream=True, stream_filter=stream_filter_mock)

            self.assertIsInstance(result, CompletedProcess)
            self.assertEqual(result.returncode, 1)
            stream_filter_mock.assert_called_once_with("line 1")


class TestSystemPackages(OdevTestCase):
    """Odev runs on systems whose package manager it does not know, and must say what is missing
    rather than dead-end on them.
    """

    @classmethod
    def setUpClass(cls):
        with patch("odev.common.odev.Odev.start", return_value=None):
            super().setUpClass()

    def setUp(self):
        super().setUp()
        self.env = PythonEnv(path=self.run_path / "venv", version="3.10")

    def on_path(self, *commands: str):
        return patch("odev.common.system.shutil.which", side_effect=lambda command: command in commands or None)

    def test_reports_without_a_known_package_manager(self):
        """Used to raise `Neither dnf or apt package managers found on the system`, which named
        neither the packages to install nor a way to move forward.
        """
        with self.on_path():
            self.assertFalse(self.env.install_system_packages())

    def test_reports_on_a_package_manager_odev_does_not_install_with(self):
        """Arch is understood well enough to name its packages, not well enough to run `sudo` on."""
        with self.on_path("pacman"):
            self.assertFalse(self.env.install_system_packages())

    def test_creation_gives_up_once_when_nothing_can_be_installed(self):
        """`create` used to retry unconditionally, asking the same question again on a system where
        the answer could not change anything.
        """
        error = RuntimeError("failed to find interpreter for Builtin discover of python_spec='3.10'")

        with (
            patch("odev.common.python.virtualenv.cli_run", side_effect=error),
            patch("odev.common.python.console.confirm", return_value=True),
            self.patch(PythonEnv, "install_system_packages", return_value=False) as install,
            self.assertRaises(OdevError),
        ):
            self.env.create()

        install.assert_called_once()


class TestDevelopmentHeaders(OdevTestCase):
    """Missing python headers are the most common reason for a source build to fail."""

    def has_headers(self, include_path: Path | None) -> bool:
        env = PythonEnv(path=self.run_path / "venv", version="3.10")
        result = None if include_path is None else CompletedProcess("", 0, stdout=f"{include_path}\n".encode())

        with self.patch(bash, "execute", return_value=result):
            return env.has_development_headers

    def test_headers_present(self):
        include_path = self.run_path / "include" / "python3.10"
        include_path.mkdir(parents=True, exist_ok=True)
        (include_path / "Python.h").write_text("", encoding="utf-8")
        self.assertTrue(self.has_headers(include_path))

    def test_headers_missing(self):
        self.assertFalse(self.has_headers(self.run_path / "include" / "python3.10"))

    def test_never_warns_on_a_guess(self):
        """An interpreter that cannot be questioned is assumed complete: a false alarm on every
        `odev run` would be worse than staying silent.
        """
        self.assertTrue(self.has_headers(None))
