"""Browser provisioning utilities."""

import shutil
import subprocess
from pathlib import Path

from odev.common.logging import logging


logger = logging.getLogger(__name__)


class Chrome:
    """Manages Chrome provisioning and wrapper generation."""

    VERSION = "145.0.7632.116"

    def __init__(self, odev):
        self.odev = odev
        self.base_path = self.odev.home_path / "browsers" / "chrome" / self.VERSION
        # Puppeteer structure: <base>/chrome/linux-<version>/chrome-linux64/chrome
        self.executable = self.base_path / "chrome" / f"linux-{self.VERSION}" / "chrome-linux64" / "chrome"

    def provision(self) -> Path | None:
        """Ensure the specific version of Chrome is installed.

        :return: Path to the Chrome executable, or None if provisioning failed.
        """
        if not self.executable.exists():
            logger.info(f"Provisioning Chrome {self.VERSION} for tours...")
            self.base_path.mkdir(parents=True, exist_ok=True)
            npx = shutil.which("npx")
            if not npx:
                logger.warning("npx not found, skipping Chrome provisioning")
                return None

            try:
                subprocess.run(  # noqa: S603
                    [
                        npx,
                        "-y",
                        "@puppeteer/browsers",
                        "install",
                        f"chrome@{self.VERSION}",
                        "--path",
                        str(self.base_path),
                    ],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to provision Chrome {self.VERSION}: {e.stderr.decode()}")
                return None
            except OSError as e:
                logger.warning(f"OS error provisioning Chrome {self.VERSION}: {e}")
                return None

        return self.executable if self.executable.exists() else None

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
