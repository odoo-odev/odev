import os
from pathlib import Path

from odev.common.config import ConfigManager
from odev.common.logging import logging


_logger: logging.Logger = logging.getLogger(__name__)


DEFAULT_VENV_NAME = "venv"


def run() -> None:
    _logger.info("Migrating db-specific venvs")
    repos_path = Path(ConfigManager("odev").get("paths", "odoo"))
    for venv_cfg_path in repos_path.glob("*/*/pyvenv.cfg"):
        venv_path = venv_cfg_path.resolve().parent
        if venv_path.name == DEFAULT_VENV_NAME:
            continue
        new_venv_path = venv_path.parent / f"venv.{venv_path.name}"
        _logger.info(f"Renaming db-specific venv [{venv_path.parent.name}]: {venv_path.name} -> {new_venv_path.name}")
        os.rename(venv_path, new_venv_path)
