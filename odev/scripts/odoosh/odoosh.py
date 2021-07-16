"""Base command classes and functionality for odoo.sh operations"""

import logging
import os.path
import subprocess
from abc import ABC
from argparse import ArgumentParser, Namespace
from typing import ClassVar, List, Optional, Mapping, Any

import time
from github import Github

from ...cli import CliCommand, CommandType, CliCommandsSubRoot
from ...utils import ShConnector, get_sh_connector, get_github


__all__ = ["CliGithubMixin", "OdooSHBase", "OdooSHBranch", "OdooSHSubRoot"]


logger = logging.getLogger(__name__)


class CliGithubMixin(CliCommand, ABC):
    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument("-t", "--token", help="Github token")

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.github: Github = get_github(args.token)


class OdooSHBase(CliCommand, ABC):
    """
    Base class with common functionality for commands running on odoo.sh
    """
    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument("-l", "--login", help="username for github / odoo.sh login")
        parser.add_argument(
            "-p", "--password", help="password for github / odoo.sh login"
        )

    @staticmethod
    def get_sh_connector_from_args(args: Namespace) -> ShConnector:
        """
        Creates an :class:`ShConnector` instance from the given parsed arguments.

        :param args: the parsed parameters as a :class:`Namespace` object.
        :return: the initialized :class:`ShConnector` instance.
        """
        logger.info("Setting up SH session")
        return get_sh_connector(args.login, args.password)

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.sh_connector: ShConnector = self.get_sh_connector_from_args(args)


class OdooSHBuildFail(RuntimeError):  # TODO: Replace with custom exc classes
    def __init__(self, *args, build_info: Mapping[str, Any], **kwargs):
        super().__init__(*args, **kwargs)
        self.build_info: Mapping[str, Any] = build_info


class OdooSHBranch(OdooSHBase, ABC):
    """
    Base class with common functionality for commands running on a odoo.sh branch
    """
    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "repo",
            metavar="REPO",
            help="the name of the SH project / github repo, " "eg. psbe-client",
        )
        parser.add_argument(
            "branch",
            metavar="BRANCH",
            help="the name of the SH branch",
        )

    def __init__(self, args: Namespace):
        if not args.repo:
            raise ValueError("Invalid SH project / repo")
        self.sh_repo: str = args.repo
        if not args.branch:
            raise ValueError("Invalid SH branch")
        self.sh_branch: str = args.branch

        super().__init__(args)

        self.ssh_url: str = self.sh_connector.get_last_build_ssh(
            self.sh_repo, self.sh_branch
        )
        self.paths_to_cleanup: List[str] = []

    def ssh_run(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """
        Run an SSH command in the current branch.
        Has the same signature as :func:`ShConnector.ssh_command` except for the
        ``ssh_url`` argument that's already provided.
        """
        return self.sh_connector.ssh_command(self.ssh_url, *args, **kwargs)

    def test_ssh(self) -> None:
        """
        Tests ssh connectivity for the odoo.sh branch
        """
        logger.debug(f"Testing SSH connectivity to SH branch {self.ssh_url}")
        result: subprocess.CompletedProcess = self.ssh_run(
            ["uname", "-a"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            logging.error(result.stdout)
            if "Permission denied (publickey)" in result.stdout:
                raise PermissionError(
                    "Got permission denied error from SSH. Did you enable ssh-agent?"
                )
            result.check_returncode()  # raises
        logger.debug(f"SSH connected successfully: {result.stdout}")

    def copy_to_sh_branch(
        self,
        *sources: str,
        dest: str,
        dest_as_dir: bool = False,
        to_cleanup: bool = False,
    ) -> None:
        """
        Copy files with rsync to the SH branch.

        :param sources: one or multiple sources to copy over.
        :param dest: the destination path to copy to.
        :param dest_as_dir: if true, ensures the ``dest`` path has a trailing `"`,
            indicating it's a directory and any sources will have to be copied into it.
            Defaults to `False`.
        :param to_cleanup: registers the copied paths for cleanup afterwards.
        """
        if dest_as_dir and not dest.endswith("/"):
            dest = dest + "/"
        if not dest.endswith("/") and len(sources) > 1:
            dest_as_dir = True
        if to_cleanup:
            # Let's set this before, so we can also clean up partial transfers
            if dest_as_dir:
                self.paths_to_cleanup += [
                    os.path.join(dest, os.path.basename(s)) for s in sources
                ]
            else:
                self.paths_to_cleanup.append(dest.rstrip("/"))
        full_dest: str = f"{self.ssh_url}:{dest}"
        sources_info: str = ", ".join(f'"{s}"' for s in sources)
        logger.debug(f'Copying {sources_info} to "{full_dest}"')
        subprocess.run(
            [
                "rsync",
                "-a",
                "--exclude=__pycache__",
                *sources,
                full_dest,
            ],
            check=True,
        )

    def wait_for_build(self, check_success: bool = False, **build_info_kwargs):
        # TODO: implement some kind of timeout?
        while True:
            time.sleep(2.5)
            build_info: Optional[Mapping[str, Any]] = self.sh_connector.build_info(
                self.sh_project, self.sh_branch, **build_info_kwargs
            )
            if not build_info:
                # TODO: Track build disappearing somehow? lookup by its id?
                continue
            build_status: str = build_info["status"]
            build_id: int = int(build_info["id"])
            if build_status == "updating":
                logger.debug(f"SH is building {build_id} on {self.sh_branch}")
                continue
            if build_status == "done":
                logger.info(f"Built {build_id} on {self.sh_branch} successfully")
                if check_success:
                    build_result: Optional[str] = build_info["result"] or None
                    if build_result != "success":
                        raise OdooSHBuildFail(
                            f"Build {build_id} on {self.sh_branch} "
                            f"not successful: {build_result}",
                            build_info=build_info,
                        )
                return build_info

    def cleanup_copied_files(self) -> None:
        """Runs cleanup of copied files previously registered for cleanup"""
        if self.paths_to_cleanup:
            logger.debug("Cleaning up copied paths")
            self.ssh_run(["rm", "-rf", *reversed(self.paths_to_cleanup)])


class OdooSHSubRoot(CliCommandsSubRoot):
    """
    SubRoot command class that prepares the argument parser for the runtime main.
    """
    command: ClassVar[CommandType] = "sh"
    help: ClassVar[Optional[str]] = "Odoo.sh subcommands"
    help_short: ClassVar[Optional[str]] = help

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        pass
