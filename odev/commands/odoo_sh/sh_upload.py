# -*- coding: utf-8 -*-

import os
from argparse import Namespace
from typing import Optional, Any, Mapping, List

from odev.structures import commands
from odev.utils import logging
from odev.exceptions import BuildWarning
from odev.exceptions import InvalidArgument, CommandAborted


logger = logging.getLogger(__name__)


REMOTE_IMPORT_DUMP_PATH: str = '/home/odoo/odoosh_import_dump.zip'


class OdooSHUploadCommand(commands.OdooSHBranchCommand):
    '''
    Command class for uploading and importing a database dump on a Odoo SH branch.
    Uploads a .zip database dump to an Odoo SH branch.
    '''

    name = 'upload'
    arguments = [
        dict(
            name='dump',
            metavar='PATH',
            help='Path to the dump file to upload to the SH branch',
        )
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path: str = args.dump

        if not os.path.exists(self.dump_path) or not os.path.isfile(self.dump_path):
            raise InvalidArgument(f'The specified dump is not a file: {self.dump_path}')
        # TODO: additional checks for .zip file with correct dump.sql/filestore fmt

    def run(self) -> Any:
        self.test_ssh()  # FIXME: move somewhere else like in OdooSH?

        build_info: Optional[Mapping[str, Any]] = self.sh_connector.build_info(self.sh_repo, self.sh_branch)
        assert build_info
        build_id = int(build_info['id'])
        build_stage: str = build_info['stage']
        project_info: Optional[Mapping[str, Any]] = self.sh_connector.project_info(self.sh_repo)
        assert project_info
        project_url: str = project_info['project_url']
        is_production: bool = build_stage == 'production'

        if is_production:
            logger.warning(
                'You are uploading a dump file to a production database, '
                'this will overwrite all existing data on this Odoo SH project'
            )

            # TODO: force doing a backup, unless explicitly disabled from cmdline?
            if not logger.confirm('Do you want to continue?'):
                raise CommandAborted()  # They weren't sure

        logger.info(
            f'Uploading dump `{os.path.basename(self.dump_path)}` '
            f'to SH `{self.sh_repo}/{self.sh_branch}`'
        )
        self.copy_to_sh_branch(
            self.dump_path,
            dest=REMOTE_IMPORT_DUMP_PATH,
            show_progress=True,
        )

        # grab last tracking id  # TODO: DRY across commands
        branch_history_before: Optional[List[Mapping[str, Any]]]
        branch_history_before = self.sh_connector.branch_history(
            self.sh_repo, self.sh_branch
        )
        last_tracking_id: int = (
            branch_history_before[0]["id"] if branch_history_before else 0
        )

        neutralize: bool = not is_production
        logger.info(f'''Starting{' neutralized ' if neutralize else ' '}database import''')
        dump_name: str = os.path.relpath(REMOTE_IMPORT_DUMP_PATH, '/home/odoo/')
        self.sh_connector.jsonrpc(
            f'{project_url}/build/{build_id}/import_database',
            params={
                'dump_name': dump_name,
                'neutralize_db': neutralize,
            },
        )
        # TODO: Check response

        logger.info(f"Waiting for SH to build with new database")
        try:  # TODO: DRY try-except block across commands
            self.wait_for_build(check_success=True, last_tracking_id=last_tracking_id)
        except BuildWarning as build_exc:
            new_build_info: Optional[Mapping[str, Any]] = build_exc.build_info
            status_info: Optional[str] = new_build_info.get("status_info")
            logger.warning(
                "SH build completed with warnings"
                + (f": {status_info}" if status_info else "")
            )
        else:
            logger.success(
                f'Database upload to "{self.sh_repo}" / "{self.sh_branch}" successful'
            )
