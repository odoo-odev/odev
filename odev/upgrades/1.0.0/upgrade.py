import re
import shutil
from pathlib import Path

from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger = logging.getLogger(__name__)

re_version = re.compile(r"^([\-a-z~0-9]+\.[0-9]+)")


def run():
    config = ConfigManager("odev")

    repos_path = Path(config.get("paths", "odoo"))

    repo_dirs = [
        p for p in repos_path.glob("*/*") if p.is_dir() and re_version.match(p.parent.name) and (p / ".git").exists()
    ]
    for directory in repo_dirs:
        _logger.warning(
            f"Folder '{directory.as_posix()}' will be deleted to improve performance by using git worktree!"
        )
        shutil.rmtree(directory)
