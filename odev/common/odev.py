"""Self update Odev by pulling latest changes from the git repository."""

import sys
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from git import Repo, Remote
from packaging import version

from odev.common.config import ConfigManager
from odev.common.logging import logging
from odev.common.python import PythonEnv
from odev.common import bash
from odev.common import prompt
from odev._version import __version__


from odev.constants import DEFAULT_DATETIME_FORMAT

logger = logging.getLogger(__name__)


ODEV_PATH: Path = Path(__file__).parents[2]
"""Local path to the odev repository."""


class Odev():
    """Main framework class."""

    version: str
    """Odev version."""

    path: Path
    """Local path to the odev repository."""

    config: ConfigManager
    """Odev configuration."""

    repo: Repo
    """Local git repository."""

    upgrades_path: Path
    """Local path to the upgrades directory."""

    def __init__(self, config: ConfigManager):
        self.version = __version__
        self.config = config
        self.path = ODEV_PATH
        self.repo = Repo(self.path)
        self.commands = {}
        self.commands_path = self.path / "odev" / "commands"
        self.upgrades_path = self.path / "odev" / "upgrades"

        if self.update():
            self.restart()

        self.register_commands()

    def update(self) -> bool:
        """
        Check for updates in the odev repository and download them if necessary.

        :param config: Odev configuration
        :return: Whether updates were pulled and installed
        :rtype: bool
        """
        if not sys.stdout.isatty() or not sys.stdin.isatty():
            return False

        if not self.__date_check_interval() or not self.__git_branch_behind():
            bash.detached(f"cd {self.path} && git fetch")
            return False

        if not self.__update_prompt():
            return False

        logger.debug(
            f"Pulling latest changes from odev repository on branch {self.repo.active_branch.tracking_branch()}"
        )
        self.config.set("update", "date", datetime.now().strftime(DEFAULT_DATETIME_FORMAT))
        install_requirements = self.__requirements_changed()
        self.repo.remotes.origin.pull()

        if install_requirements:
            logger.debug("Installing new odev package requirements")
            PythonEnv().install_requirements(self.path)

        self.upgrade()

        return True

    def restart() -> None:
        """Restart the current process with the latest version of odev."""
        logger.debug("Restarting odev")
        os.execv(sys.argv[0], sys.argv)

    def check_upgrade(self) -> bool:
        """Check whether the current version of odev is the latest available version.

        :return: Whether the current version is the latest available version
        :rtype: bool
        """
        logger.debug("Checking for existing odev upgrades")
        return version.parse(self.version) > version.parse(self.__latest_version())

    def upgrade(self) -> None:
        """Upgrade the current version of odev."""
        if not self.check_upgrade():
            return

        current_version = self.__latest_version()

        logger.debug(f"Upgrading odev from version {current_version} to {self.version}")
        scripts = self.__list_upgrade_scripts()

        for script in scripts:
            logger.debug(f"Running upgrade script [{current_version} -> {script.parent.name}]")
            self.__run_upgrade_script(script)

        self.config.set("update", "version", self.version)
        return True


    # --- Private methods ------------------------------------------------------

    def __git_branch_behind(self) -> bool:
        """Assess whether the current branch is behind the remote tracking branch.

        :param repo: Git repository
        :param branch: Branch to check
        :return: Whether the branch is behind the remote tracking branch
        :rtype: bool
        """
        remote_branch = self.repo.active_branch.tracking_branch()

        if remote_branch is None:
            return False

        remote: Remote = self.repo.remotes[remote_branch.remote_name]
        rev_list: str = self.repo.git.rev_list('--left-right', '--count', f'{remote.name}...HEAD')
        commits_behind, commits_ahead = [int(commits_count) for commits_count in rev_list.split('\t')]
        message_behind = f"{commits_behind} commit{'s' if commits_behind > 1 else ''} behind"
        message_ahead = f"{commits_ahead} commit{'s' if commits_ahead > 1 else ''} ahead of"

        if commits_behind and commits_ahead:
            logger.debug(f"Odev is {message_behind} and {message_ahead} {remote.name}")
        elif commits_behind:
            logger.debug(f"Odev is {message_behind} {remote.name}")
        elif commits_ahead:
            logger.debug(f"Odev is {message_ahead} {remote.name}")
        else:
            logger.debug(f"Odev is up-to-date with {remote.name}")

        if commits_ahead:
            logger.debug("Running in development mode (no self-update)")
            return False

        return bool(commits_behind)

    def __requirements_changed(self) -> bool:
        """Assess whether the requirements.txt file was modified.

        :param repo: Git repository
        :return: Whether the requirements.txt file has changed
        :rtype: bool
        """
        requirements_file = self.path / "requirements.txt"
        diff = self.repo.git.diff("--name-only", "HEAD", requirements_file).strip()

        if diff == str(requirements_file):
            logger.debug("Odev requirements have changed since last version")

        return bool(diff)

    def __date_check_interval(self) -> bool:
        """Check whether the last check date is older than today minus the check interval.

        :param config: Odev configuration
        :return: Whether the last check date is older than today minus the check interval
        :rtype: bool
        """
        default_date = (datetime.today() - timedelta(days=1)).strftime(DEFAULT_DATETIME_FORMAT)
        check_date = self.config.get("update", "date", default_date)
        check_interval = int(self.config.get("update", "interval", 1))
        check_diff = (datetime.today() - datetime.strptime(check_date, DEFAULT_DATETIME_FORMAT)).days
        return check_diff >= check_interval

    def __update_prompt(self) -> bool:
        """Prompt the user to update odev if a new version is available.

        :param config: Odev configuration
        :return: Whether the user wants to update odev
        :rtype: bool
        """
        update_mode = self.config.get("update", "mode", "ask")
        assert update_mode in ("ask", "always", "never")

        if update_mode == "ask":
            return prompt.confirm("An update is available for odev, do you want to download it now?")

        return update_mode == "always"

    def __latest_version(self) -> str:
        """Get the latest version of odev from the config file.

        :return: Latest version of odev
        :rtype: str
        """
        return self.config.get("update", "version", self.config.get("odev", "version", self.version))

    def __validate_upgrade_script(self, script: Path) -> bool:
        """Validate the upgrade script's version to check whether it should be run.

        :param script: Upgrade script's path
        :return: Whether the upgrade script should be run
        :rtype: bool
        """
        script_version = version.parse(script.parent.name)

        return not any([
            not script.is_file(),
            re.match(r"^(\d+\.){2}\d+$", script.parent.name) is None,
            script_version <= version.parse(self.__latest_version()),
            script_version > version.parse(self.version),
        ])

    def __list_upgrade_scripts(self) -> List[Path]:
        """List the upgrade scripts that should be run.

        :return: Upgrade scripts that should be run
        :rtype: List[Path]
        """
        return sorted(
            (s for s in self.upgrades_path.rglob("*.py") if self.__validate_upgrade_script(s)),
            key=lambda s: version.parse(s.parent.name),
        )

    def __run_upgrade_script(self, script: Path) -> None:
        """Run an upgrade script.

        :param script: Upgrade script's path
        """
        spec = importlib.util.spec_from_file_location(script.stem, str(script))
        assert spec is not None and spec.loader is not None
        script_module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script_module)
        script_module.run(self.config)
