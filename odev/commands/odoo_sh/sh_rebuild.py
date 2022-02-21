from typing import Any, Mapping, Optional

from odev.exceptions import BuildWarning, CommandAborted, InvalidBranch
from odev.structures import commands
from odev.utils import logging
from odev.utils.logging import term


_logger = logging.getLogger(__name__)


class OdooSHRebuildCommand(commands.OdooSHBranchCommand):
    """
    Launch a rebuild of a branch on Odoo SH.
    """

    name = "rebuild"

    def run(self) -> Any:
        branch_info = self.sh_connector.branch_info(self.sh_branch)
        assert branch_info is not None

        if branch_info["stage"] == "production":
            raise InvalidBranch(
                f"Branch {self.sh_repo}/{self.sh_branch} is a production branch " "and cannot be rebuilt"
            )
        if branch_info["stage"] == "staging":
            # TODO: force doing a backup, unless explicitly disabled from cmdline?
            _logger.warning(
                f"""You are about to rebuild a {term.bold('staging')} branch. """
                f"The current database will be replaced with a copy of the production branch "
                f"and all data currently existing on {self.sh_branch} will be lost."
            )

            if not _logger.confirm("Are you sure you want to continue?"):
                raise CommandAborted()

        # grab last tracking id  # TODO: DRY across commands
        branch_history_before = self.sh_connector.branch_history(self.sh_branch)
        last_tracking_id: int = branch_history_before[0]["id"] if branch_history_before else 0

        _logger.info(f'Rebuilding SH project "{self.sh_repo}" branch "{self.sh_branch}"')
        result: Any = self.sh_connector.branch_rebuild(self.sh_branch)
        if not isinstance(result, bool) or not result:
            result_info: str = str(result)
            if isinstance(result, dict) and "error" in result:
                result_info = str(result["error"])
            raise RuntimeError(f"Failed rebuilding branch {self.sh_repo}/{self.sh_branch}:\n" + result_info)

        _logger.info("Waiting for SH rebuild to complete...")

        # TODO: make sure it's the right build, and doesn't get swapped
        try:
            self.wait_for_build(check_success=True, last_tracking_id=last_tracking_id)
        except BuildWarning as build_exc:
            new_build_info: Optional[Mapping[str, Any]] = build_exc.build_info
            status_info: Optional[str] = new_build_info.get("status_info")
            _logger.warning("SH build completed with warnings" + (f": {status_info}" if status_info else ""))
        else:
            _logger.success(f"Branch {self.sh_repo}/{self.sh_branch} rebuilt successfully")
