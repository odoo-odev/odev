"""Upgrade to odev 4.22.0.

Moving the plugins folder to the odev config directory.
"""

from odev.common.config import CONFIG_DIR
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


def run(odev: Odev) -> None:
    source = odev.base_path / "plugins"
    destination_dir = CONFIG_DIR / "plugins"

    destination_dir.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        destination = destination_dir / item.name

        target = item.resolve()
        destination.symlink_to(target)
        item.unlink()

    source.rmdir()

    logger.info("Plugins folder has been correctly moved to the odev config directory.")
