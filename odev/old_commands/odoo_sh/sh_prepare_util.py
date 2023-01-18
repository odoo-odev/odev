"""Prepare odoo.sh and local repo to use `util` and `custom_util`"""

import os.path
import re
from argparse import Namespace
from typing import ClassVar, List, Optional, Tuple

from git import Repo, Submodule

from odev.commands.odoo_sh import sh_submodule
from odev.utils import logging
from odev.utils.github import GitCommitContext


_logger: logging.Logger = logging.getLogger(__name__)


class OdooSHPrepareUtilCommand(sh_submodule.OdooSHSubmoduleCommand):
    """
    Prepare an odoo.sh project and its local repository clone for using `util` and `custom_util`
    (from the `util_package` repository) when doing builds and running modules' migration scripts.
    """

    default_commit_msg: ClassVar[Optional[str]] = "[UPG] add `{module_name}` submodule"
    default_update_msg: ClassVar[Optional[str]] = "[UPG] update `{module_name}` submodule to {module_commit}"

    name = "prepare-util"
    arguments = [
        {
            "name": "module_url",
            "nargs": "?",
            "default": "git@github.com:odoo-ps/util_package.git",
            "help": "URL to the `util_package` repository",
        },
        {
            "name": "module_path",
        },
        {
            "name": "commit",
            "aliases": ["--commit"],
            "default": True,
        },
    ]

    base_path_on_sh: ClassVar[str] = "/home/odoo/src/user"
    requirements_magic_comment: ClassVar[str] = "generated by odev prepare-util"

    def __init__(self, args: Namespace):
        if args.no_local:
            args.commit = None
            args.update = None

        super().__init__(args)

    def _add_requirements(self, git_submodule: Submodule) -> Tuple[str, bool]:
        requirements_filename: str = "requirements.txt"
        requirements_path: str = os.path.join(self.local_repo_path, requirements_filename)

        _logger.info("Adding 'util_package' to local repo's 'requirements.txt'")

        requirements: List[str] = []
        requirements_before: Optional[List[str]] = None
        if os.path.exists(requirements_path):
            with open(requirements_path, "r") as fp:
                requirements_before = fp.readlines()

            requirements = [
                line
                for line in requirements_before
                if not re.search(rf"#\s*{self.requirements_magic_comment}$", line.strip(), re.I)
            ]

        util_package_sh_path: str = f"{self.base_path_on_sh}/{git_submodule.path}"
        util_package_requirement: str = f"file:{util_package_sh_path}"
        requirements.append(f"{util_package_requirement}  # {self.requirements_magic_comment}\n")

        with open(requirements_path, "w") as fp:
            fp.writelines(requirements)

        changed: bool = requirements != requirements_before

        return requirements_filename, changed

    def _add_local_submodule(self, repo: Repo, commit_context: Optional[GitCommitContext]) -> Tuple[Submodule, bool]:
        git_submodule: Submodule
        just_added: bool
        git_submodule, just_added = super()._add_local_submodule(repo, commit_context)

        requirements_filename: str
        requirements_changed: bool
        requirements_filename, requirements_changed = self._add_requirements(git_submodule)
        if requirements_changed:
            commit_context.add(requirements_filename)

        return git_submodule, (just_added or requirements_changed)