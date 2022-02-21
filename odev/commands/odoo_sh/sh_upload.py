import os
import re
import zipfile
from argparse import Namespace
from typing import Any, Mapping, Optional

from odev.exceptions import BuildWarning, CommandAborted, InvalidArgument
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


REMOTE_IMPORT_DUMP_PATH: str = "/home/odoo/odoosh_import_dump.zip"


class OdooSHUploadCommand(commands.OdooSHBranchCommand):
    """
    Command class for uploading and importing a database dump on a Odoo SH branch.
    Uploads a .zip database dump to an Odoo SH branch.
    """

    name = "upload"
    arguments = [
        {
            "name": "dump",
            "metavar": "PATH",
            "help": "Path to the dump file to upload to the SH branch",
        },
        {
            "name": "--keep-filestore",
            "action": "store_true",
            "help": "Prevent SH from deleting the filestore on subsequent uploads",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path: str = args.dump
        self.keep_filestore: bool = args.keep_filestore

        if not os.path.exists(self.dump_path) or not os.path.isfile(self.dump_path):
            raise InvalidArgument(f"The specified dump is not a file: {self.dump_path}")

        self._validate_dump_file(self.dump_path)

    @classmethod
    def _validate_dump_file(cls, dump_file_path: str):
        """
        Check dump file is in the correct format for SH upload
        :param dump_file_path: the dump file path
        """
        path, ext = os.path.splitext(dump_file_path)
        if ext == ".zip":  # TODO: what if it's not a zip file?
            # regex to match filestore paths in zipfile
            fs_regex = re.compile(r"(filestore/)(?:checklist/)?(?:[a-z\d]{2}/[a-z\d]{40})?")
            # mandatory
            required_zipfile_content = {"filestore/", "dump.sql"}
            with zipfile.ZipFile(dump_file_path) as dump_zipfile:
                for member in dump_zipfile.namelist():
                    m = fs_regex.match(member)  # filestore path
                    if m:
                        if m.group(1) in required_zipfile_content:
                            required_zipfile_content.remove(m.group(1))
                        else:
                            continue
                    else:  # dump.sql
                        try:
                            required_zipfile_content.remove(member)
                        except KeyError:
                            raise RuntimeError(f"Unknown file in zipped dump: {member}")
                if required_zipfile_content:
                    raise RuntimeError(f"Zipped dump does not contain mandatory member(s): {required_zipfile_content}")

    def run(self) -> Any:
        self.test_ssh()  # FIXME: move somewhere else like in OdooSH?

        build_info = self.sh_connector.build_info(self.sh_branch)
        assert build_info is not None
        build_id: int = int(build_info["id"])
        build_stage: str = build_info["stage"]
        project_info: Optional[Mapping[str, Any]]
        project_info = self.sh_connector.project_info()
        assert project_info is not None
        project_url: str = project_info["project_url"]
        is_production: bool = build_stage == "production"

        if is_production:
            _logger.warning(
                "You are uploading a dump file to a production database, "
                "this will overwrite all existing data on this Odoo SH project"
            )

            # TODO: force doing a backup, unless explicitly disabled from cmdline?
            if not _logger.confirm("Do you want to continue?"):
                raise CommandAborted()  # They weren't sure

        if self.keep_filestore:
            _logger.info("Hardlink-cloning existing filestore to preserve it")
            self.ssh_run(["bash", "-c", "cp -al ~/data/filestore/* ~/data/filestore.backup"])

        _logger.info(f"Uploading dump `{os.path.basename(self.dump_path)}` " f"to SH `{self.sh_repo}/{self.sh_branch}`")
        self.copy_to_sh_branch(
            self.dump_path,
            dest=REMOTE_IMPORT_DUMP_PATH,
            show_progress=True,
        )

        # grab last tracking id  # TODO: DRY across commands
        branch_history_before = self.sh_connector.branch_history(self.sh_branch)
        last_tracking_id: int = branch_history_before[0]["id"] if branch_history_before else 0

        neutralize: bool = not is_production
        _logger.info(f"""Starting{' neutralized ' if neutralize else ' '}database import""")
        dump_name: str = os.path.relpath(REMOTE_IMPORT_DUMP_PATH, "/home/odoo/")
        self.sh_connector.jsonrpc(
            f"{project_url}/build/{build_id}/import_database",
            params={
                "dump_name": dump_name,
                "neutralize_db": neutralize,
            },
        )
        # TODO: Check response

        _logger.info("Waiting for SH to build with new database...")
        try:  # TODO: DRY try-except block across commands
            self.wait_for_build(check_success=True, last_tracking_id=last_tracking_id)
        except BuildWarning as build_exc:
            new_build_info: Optional[Mapping[str, Any]] = build_exc.build_info
            status_info: Optional[str] = new_build_info.get("status_info")
            _logger.warning("SH build completed with warnings" + (f": {status_info}" if status_info else ""))
        else:
            _logger.success(f'Database upload to "{self.sh_repo}" / "{self.sh_branch}" successful')
        finally:
            if self.keep_filestore:
                _logger.info("Restoring and merging previous filestore")
                self.ssh_run(
                    [
                        "bash",
                        "-c",
                        "cp -aluf ~/data/filestore.backup/* ~/data/filestore/*/ " "&& rm -r ~/data/filestore.backup",
                    ]
                )
