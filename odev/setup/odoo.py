"""Import Odoo repositories if already downloaded."""

import shutil
from pathlib import Path

from odev.common.console import console
from odev.common.logging import logging
from odev.common.odev import Odev


logger = logging.getLogger(__name__)


PRIORITY = 30

ODOO_REPOSITORIES = ["odoo", "enterprise", "design-themes"]


# --- Setup --------------------------------------------------------------------


def setup(odev: Odev) -> None:
    """Import Odoo repositories if already downloaded.
    :param config: Odev configuration
    """
    if not console.confirm("Have you already downloaded Odoo repositories on this computer?"):
        return logger.info("Skipping Odoo repositories import, they will be downloaded when needed")

    new_parent_path = odev.config.paths.repositories / "odoo"
    old_parent_dir = console.directory(
        "Path to the parent directory of your local Odoo repositories",
        default=(new_parent_path).as_posix(),
    )

    if old_parent_dir is None:
        return logger.warning("Skipping Odoo repositories import, no parent directory provided")

    old_parent_path = Path(old_parent_dir).resolve()

    if old_parent_path == new_parent_path:
        return logger.warning("Skipping Odoo repositories import, path is identical to the new one")

    new_parent_path.mkdir(parents=True, exist_ok=True)

    action = console.select(
        "What do you want to do with the existing repositories?",
        choices=[
            ("move", "Move files to the new parent directory (recommended)"),
            ("link", "Create a symbolic link to the new parent directory (if other tools rely on those directories)"),
            ("copy", "Copy files to the new parent directory (safest but will double the space used on disk)"),
        ],
    )

    repositories = sorted(
        (
            repository.name
            for repository in old_parent_path.iterdir()
            if repository.is_dir() and (repository / ".git").is_dir()
        ),
        key=lambda repo: ODOO_REPOSITORIES.index(repo.lower()) if repo.lower() in ODOO_REPOSITORIES else 999,
    )

    if not repositories:
        return logger.info("No repositories found in the old parent directory")

    repositories = console.checkbox(
        f"Which repositories do you want to {action}?",
        choices=[(repo, None) for repo in repositories],
        defaults=list(set(repositories) & set(ODOO_REPOSITORIES)),
    )

    for repo in repositories:
        old_repo_path = old_parent_path / repo
        new_repo_path = new_parent_path / repo

        if new_repo_path.exists():
            logger.warning(f"Path {new_repo_path} already exists")

            if console.confirm("Would you like to overwrite it?"):
                logger.debug(f"Removing {new_repo_path}")
                shutil.rmtree(new_repo_path)
            else:
                logger.debug(f"Skipping {new_repo_path}")
                continue

        if old_repo_path.exists():
            match action:
                case "move":
                    logger.debug(f"Moving {old_repo_path} to {new_repo_path}")
                    shutil.move(old_repo_path, new_repo_path)
                case "link":
                    logger.debug(f"Creating symlink from {old_repo_path} to {new_repo_path}")
                    new_repo_path.symlink_to(old_repo_path)
                case "copy":
                    logger.debug(f"Copying {old_repo_path} to {new_repo_path}")
                    shutil.copytree(old_repo_path, new_repo_path)
        else:
            logger.debug(f"Path {old_repo_path} does not exist, skipping")

    logger.info(f"Moved {len(repositories)} repositories to {new_parent_path}")
