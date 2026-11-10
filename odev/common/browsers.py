"""Browser provisioning utilities."""

import re
import shutil
import tempfile
import zipfile
from functools import lru_cache
from pathlib import Path

import requests

from odev.common.logging import logging


logger = logging.getLogger(__name__)


class Chrome:
    """Manages Chrome provisioning and wrapper generation."""

    VERSION = "145.0.7632.116"
    """Fallback version if Runbot fetching fails."""

    DOWNLOAD_URL = "https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/chrome-linux64.zip"
    """Chrome for Testing archive, the same one `npx @puppeteer/browsers install` fetches."""

    @classmethod
    @lru_cache(maxsize=1)
    def fetch_version(cls) -> str:
        """Fetch the latest Chrome version used by Runbot.

        :return: The Chrome version string (e.g., "145.0.7632.116").
        """
        url = "https://runbot.odoo.com/runbot/dockerfile/tag/odoo:DockerMaster"
        try:
            logger.debug(f"Fetching Chrome version from {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            # Parse version from: # Install chrome with values {"chrome_version": "145.0.7632.116-1"}
            match = re.search(r'chrome_version": "([\d\.]+)', response.text)
            if match:
                return match.group(1)
        except requests.RequestException as e:
            logger.warning(f"Could not fetch Chrome version from Runbot: {e}")

        return cls.VERSION

    def __init__(self, odev):
        self.odev = odev
        self.version = self.fetch_version()
        self.base_path = self.odev.home_path / "browsers" / "chrome" / self.version
        # Puppeteer structure: <base>/chrome/linux-<version>/chrome-linux64/chrome
        self.executable = self.base_path / "chrome" / f"linux-{self.version}" / "chrome-linux64" / "chrome"

    def provision(self) -> Path | None:
        """Ensure the specific version of Chrome is installed.

        :return: Path to the Chrome executable, or None if provisioning failed.
        """
        if not self.executable.exists():
            logger.info(f"Provisioning Chrome {self.version} for tours...")

            try:
                self._download()
            except (requests.RequestException, zipfile.BadZipFile, OSError) as e:
                logger.warning(f"Failed to provision Chrome {self.version}: {e}")
                return None

        return self.executable if self.executable.exists() else None

    def _download(self) -> None:
        """Download and unpack Chrome for Testing where `self.executable` expects it.

        The archive is unpacked next to its destination and moved in place only once
        complete, so an interrupted download never leaves a broken install behind that
        `provision` would then mistake for a finished one.
        """
        install_dir = self.executable.parent.parent  # <base>/chrome/linux-<version>
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=install_dir.parent, prefix=".download-") as tmp:
            archive = Path(tmp) / "chrome-linux64.zip"
            extracted = Path(tmp) / "extracted"
            url = self.DOWNLOAD_URL.format(version=self.version)
            logger.debug(f"Downloading Chrome from {url}")

            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()

                with archive.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        file.write(chunk)

            with zipfile.ZipFile(archive) as zip_file:
                for member in zip_file.infolist():
                    path = Path(zip_file.extract(member, extracted))

                    # `zipfile` drops Unix permissions, without which Chrome cannot run.
                    if mode := (member.external_attr >> 16) & 0o777:
                        path.chmod(mode)

            shutil.rmtree(install_dir, ignore_errors=True)
            extracted.rename(install_dir)

    def get_wrapper(self, chrome_bin: Path | None = None) -> Path:
        """Create a Chrome wrapper script with consistent rendering flags.

        :param chrome_bin: Optional path to the Chrome binary to use.
        :return: Path to the generated wrapper script.
        """
        tmp_dir = self.odev.home_path / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wrapper = tmp_dir / "odoo-chrome-wrapper"

        search_bins = "google-chrome chromium chromium-browser google-chrome-stable"
        if chrome_bin:
            search_bins = f"{chrome_bin} {search_bins}"

        wrapper.write_text(
            "#!/bin/bash\n"
            f"for bin in {search_bins}; do\n"
            '    real=$(command -v "$bin" 2>/dev/null)\n'
            '    if [ -n "$real" ]; then\n'
            '        exec "$real" \\\n'
            "            --font-render-hinting=none \\\n"
            "            --force-device-scale-factor=1 \\\n"
            "            --disable-font-subpixel-positioning \\\n"
            "            --hide-scrollbars \\\n"
            "            --window-size=1366,768 \\\n"
            "            --no-sandbox \\\n"
            '            "$@"\n'
            "    fi\n"
            "done\n"
            'echo "Chrome not found" >&2\n'
            "exit 1\n"
        )
        wrapper.chmod(0o755)
        return wrapper
