from typing import Optional, Any, Mapping, List

from odev.structures import commands
from odev.utils import logging
from odev.utils.logging import term
from odev.exceptions import BuildWarning, InvalidBranch, CommandAborted


logger = logging.getLogger(__name__)


class OdooSHRebuildCommand(commands.OdooSHBranchCommand):
    '''
    Launch a rebuild of a branch on Odoo SH.
    '''

    name = 'rebuild'

    def run(self):
        branch_info = self.sh_connector.branch_info(self.sh_repo, self.sh_branch)
        assert branch_info

        if branch_info['stage'] == 'production':
            raise InvalidBranch(
                f'Branch {self.sh_repo}/{self.sh_branch} is a production branch '
                'and cannot be rebuilt'
            )
        if branch_info['stage'] == 'staging':
            # TODO: force doing a backup, unless explicitly disabled from cmdline?
            logger.warning(
                f'''You are about to rebuild a {term.bold('staging')} branch. '''
                f'The current database will be replaced with a copy of the production branch '
                f'and all data currently existing on {self.sh_branch} will be lost.'
            )

            if not logger.confirm('Are you sure you want to continue?'):
                raise CommandAborted()

        # grab last tracking id  # TODO: DRY across commands
        branch_history_before: Optional[List[Mapping[str, Any]]]
        branch_history_before = self.sh_connector.branch_history(
            self.sh_repo, self.sh_branch
        )
        last_tracking_id: int = (
            branch_history_before[0]["id"] if branch_history_before else 0
        )

        logger.info(f'Rebuilding SH project "{self.sh_repo}" branch "{self.sh_branch}"')
        result: Any = self.sh_connector.branch_rebuild(self.sh_repo, self.sh_branch)

        if not isinstance(result, bool) or not result:
            result_info: str = str(result)
            if isinstance(result, dict) and 'error' in result:
                result_info = str(result['error'])
            raise RuntimeError(
                f'Failed rebuilding branch {self.sh_repo}/{self.sh_branch}:\n'
                + result_info
            )

        logger.info(f'Waiting for SH rebuild to complete')

        # TODO: make sure it's the right build, and doesn't get swapped
        try:
            self.wait_for_build(check_success=True, last_tracking_id=last_tracking_id)
        except BuildWarning as build_exc:
            new_build_info: Optional[Mapping[str, Any]] = build_exc.build_info
            status_info: Optional[str] = new_build_info.get('status_info')
            logger.warning(
                "SH build completed with warnings"
                + (f": {status_info}" if status_info else "")
            )
        else:
            logger.success(f'Branch {self.sh_repo}/{self.sh_branch} rebuilt successfully')
