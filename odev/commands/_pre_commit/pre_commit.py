import os
import subprocess
import sys
from argparse import Namespace

from git import Repo

from odev import exceptions
from odev.exceptions import GitEmptyStagingException, InvalidArgument
from odev.structures import commands
from odev.utils import logging
from odev.utils.github import is_git_repo
from odev.utils.odoo import get_odoo_version
from odev.utils.pre_commit import fetch_pre_commit_config


_logger = logging.getLogger(__name__)


class PreCommitCommand(commands.LocalDatabaseCommand):
    """
    This command can be used to install/update the pre-commit configuration
    to the target version, supplied as an existing Odoo database name or a
    valid Odoo version. It uses the git repo in the current working directory
    and automatically creates a commit for the downloaded configuration.
    """

    name = "pre-commit"

    database_required = False
    add_database_argument = False

    repo: Repo
    version: str
    staged_files: bool

    arguments = [
        {
            "name": "target",
            "help": (
                "An existing Odoo database name or valid Odoo version to target for "
                "downloading and committing the pre-commit configuration"
            ),
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.repo = self.get_repo()
        self.version = self.get_target_version()

        if self.repo.untracked_files:
            _logger.error("Untracked files detected in repo... stage or commit them before running this command!")
            sys.exit(1)

        self.staged_files = False
        if self.repo.index.diff("HEAD"):
            self.staged_files = True
            self.repo.git.stash("push")

    def run(self) -> int:
        _logger.info(f"Fetching latest pre-commit config for Odoo version {self.version}")

        try:
            fetch_pre_commit_config(dst_path=self.repo.working_tree_dir, version=self.version)

            self.repo.git.add(".")
            if not self.repo.index.diff("HEAD"):
                raise GitEmptyStagingException()

            self.repo.git.commit("-m", self.get_commit_msg())

        except GitEmptyStagingException:
            _logger.info("pre-commit config is already up-to-date")
            sys.exit(0)

        else:
            self.run_pre_commit_install()

        finally:
            self.staged_files and self.repo.git.stash("pop")

        return 0

    def get_repo(self) -> Repo:
        if not is_git_repo(os.getcwd()):
            raise InvalidArgument("No git repository found at current working directory!")

        return Repo(os.getcwd())

    def get_target_version(self) -> str:
        try:
            return self.db_version_clean(database=self.args.target)
        except (exceptions.InvalidOdooDatabase, exceptions.InvalidDatabase):
            pass

        try:
            return get_odoo_version(self.args.target)
        except exceptions.InvalidVersion:
            pass

        raise InvalidArgument(
            "Unable to parse the target argument... use an existing Odoo db name or a valid Odoo version!"
        )

    def get_commit_msg(self) -> str:
        return (
            f":heart_eyes: add pre-commit config for version {self.version}\n\n"
            "see https://github.com/odoo-ps/psbe-process/wiki/Development-common-practices#pre-commit"
        )

    def run_pre_commit_install(self) -> None:
        try:
            subprocess.check_output(["pre-commit", "install"], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as error:
            _logger.debug(error.output.decode("utf-8"))
            _logger.info(
                "pre-commit config downloaded, but unable to install... try running `pre-commit install` manually"
            )
            sys.exit(1)

        _logger.info("Done!")
