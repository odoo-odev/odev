import os
import glob
import git
from argparse import Namespace

from odev.exceptions import InvalidVersion, InvalidArgument
from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.odoo import version_from_branch, prepare_odoobin
from odev.utils.config import ConfigManager
_logger = logging.getLogger(__name__)

class PullCommand(commands.Command):
    """
    Update a odoo source folder to it latest revision or update them all
    """

    name = "pull"
    arguments = [
        dict(
            aliases=["-f", "--force"],
            dest='force',
            action='store_true',
            help="Force reset in case of conflict",
        ),
        dict(
            aliases=["version"],
            nargs='?',
            default="",
            help="Odoo version to update",
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

    def run(self):
        config = ConfigManager("odev")
        odoo_path = config.get("paths", "odoo")

        worktree_list = git.Repo(odoo_path + "/master/odoo").git.worktree('list', '--porcelain')
        odoo_version = [os.path.basename(b) for b in worktree_list.split("\n") if "branch" in b and "master" not in b]

        if self.args.version:
            try:
                version = odoo.get_odoo_version(self.args.version)
            except InvalidVersion as exc:
                raise InvalidArgument(str(exc)) from exc

            odoo_version = [p for p in odoo_version if version == p[1]]

        for version in odoo_version:
            version = version_from_branch(version)

            prepare_odoobin(odoo_path, version, venv=False, upgrade=False, skip_prompt=self.args.force)
