import logging
import os
import time
from argparse import ArgumentParser, Namespace
from typing import ClassVar, Optional, Type, Any, Mapping

from .odoosh import OdooSHBranch, OdooSHSubRoot
from ...cli import CliCommandsSubRoot, CommandType
from ...log import term
from ...utils import utils


__all__ = ["OdooSHUpload"]


logger = logging.getLogger(__name__)


REMOTE_IMPORT_DUMP_PATH: str = "/home/odoo/odoosh_import_dump.zip"


class OdooSHUpload(OdooSHBranch):
    """
    Command class for uploading and importing a database dump on a odoo.sh branch.
    """

    parent: ClassVar[Optional[Type[CliCommandsSubRoot]]] = OdooSHSubRoot
    command: ClassVar[CommandType] = "upload"
    help: ClassVar[Optional[str]] = "Uploads a .zip database dump to an SH branch."
    help_short: ClassVar[Optional[str]] = help

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "dump",
            metavar="PATH",
            help="Path to the dump file to upload to the SH branch",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path: str = args.dump
        if not os.path.exists(self.dump_path) or not os.path.isfile(self.dump_path):
            raise RuntimeError(f"The specified dump is not a file: {self.dump_path}")
        # TODO: additional checks for .zip file with correct dump.sql/filestore fmt

    def run(self) -> Any:
        self.test_ssh()  # FIXME: move somewhere else like in OdooSH?

        build_info: Optional[Mapping[str, Any]]
        build_info = self.sh_connector.build_info(self.sh_repo, self.sh_branch)
        build_id: int = int(build_info["id"])
        build_stage: str = build_info["stage"]
        project_info: Optional[Mapping[str, Any]]
        project_info = self.sh_connector.project_info(self.sh_repo)
        project_url: str = project_info["project_url"]
        is_production: bool = build_stage == "production"

        if is_production:
            # TODO: force doing a backup, unless explicitly disabled from cmdline?
            if not utils.confirm(
                term.orangered("You are uploading a dump on production. ")
                + term.gold("Are you sure of what you're doing?")
            ):
                raise RuntimeError("Aborted")  # They weren't sure

        logger.info(
            f'Uploading dump "{os.path.basename(self.dump_path)}" '
            f'to SH "{self.sh_repo}" / "{self.sh_branch}"'
        )
        self.copy_to_sh_branch(self.dump_path, dest=REMOTE_IMPORT_DUMP_PATH)

        neutralize: bool = not is_production
        logger.info(
            f"Starting database import"
            + (" (will be neutralized)" if neutralize else "")
        )
        dump_name: str = os.path.relpath(REMOTE_IMPORT_DUMP_PATH, "/home/odoo/")
        self.sh_connector.jsonrpc(
            f"{project_url}/build/{build_id}/import_database",
            params={
                "dump_name": dump_name,
                "neutralize_db": neutralize,
            },
        )
        # TODO: Check response

        logger.info(f"Waiting for SH to build with new database")
        time.sleep(2.5)
        # TODO: make sure it's the right build, and doesn't get swapped
        self.wait_for_build(check_success=True)

        logger.success(
            f'Database upload to "{self.sh_repo}" / "{self.sh_branch}" successful'
        )
