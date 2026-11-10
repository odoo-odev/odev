import io
import os
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests

from odev.common.browsers import Chrome


VERSION = "145.0.7632.116"


def _archive() -> bytes:
    """Build a tiny stand-in for the Chrome for Testing archive."""
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, mode in (("chrome-linux64/chrome", 0o755), ("chrome-linux64/resources.pak", 0o644)):
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100000 | mode) << 16
            zip_file.writestr(info, b"binary")

    return buffer.getvalue()


def _response(content: bytes = b"", error: Exception | None = None) -> MagicMock:
    """Mock the context manager returned by `requests.get(..., stream=True)`."""
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [content]

    if error is not None:
        response.raise_for_status.side_effect = error

    return response


class TestCommonBrowsers(TestCase):
    """Test the provisioning of the Chrome used for tours."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)

        with patch.object(Chrome, "fetch_version", return_value=VERSION):
            self.chrome = Chrome(SimpleNamespace(home_path=Path(self.home.name)))

    def test_01_provision_downloads_chrome(self):
        """Chrome for Testing is unpacked where `executable` expects it, still executable."""
        with patch("odev.common.browsers.requests.get", return_value=_response(_archive())) as get:
            self.assertEqual(self.chrome.provision(), self.chrome.executable)

        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], Chrome.DOWNLOAD_URL.format(version=VERSION))
        self.assertTrue(os.access(self.chrome.executable, os.X_OK))
        self.assertFalse(os.access(self.chrome.executable.with_name("resources.pak"), os.X_OK))

    def test_02_provision_reuses_existing_chrome(self):
        """An installed Chrome is not downloaded again."""
        self.chrome.executable.parent.mkdir(parents=True)
        self.chrome.executable.touch()

        with patch("odev.common.browsers.requests.get") as get:
            self.assertEqual(self.chrome.provision(), self.chrome.executable)

        get.assert_not_called()

    def test_03_provision_failure_leaves_nothing_behind(self):
        """A failed download returns None and leaves no partial install to mistake for a real one."""
        error = requests.HTTPError("404 Not Found")

        with patch("odev.common.browsers.requests.get", return_value=_response(error=error)):
            self.assertIsNone(self.chrome.provision())

        self.assertFalse(self.chrome.executable.parent.parent.exists())
        self.assertEqual(list(self.chrome.base_path.joinpath("chrome").iterdir()), [])

    def test_04_provision_corrupt_archive(self):
        """A truncated archive is reported as a failure rather than raised."""
        with patch("odev.common.browsers.requests.get", return_value=_response(b"not a zip")):
            self.assertIsNone(self.chrome.provision())

        self.assertFalse(self.chrome.executable.exists())
