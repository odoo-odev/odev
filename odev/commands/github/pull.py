from argparse import Namespace

from odev.constants import ODOO_MASTER_REPO
from odev.exceptions import InvalidArgument, InvalidVersion
from odev.structures import commands
from odev.utils import logging, odoo
from odev.utils.config import ConfigManager
from odev.utils.github import get_worktree_list
from odev.utils.odoo import prepare_odoobin, version_from_branch


_logger = logging.getLogger(__name__)


class PullCommand(commands.Command):
    """
    Update a odoo source folder to it latest revision or update them all
    """

    name = "pull"
    arguments = [
        {
            "aliases": ["-f", "--force"],
            "dest": "force",
            "action": "store_true",
            "help": "Force reset in case of conflict",
        },
        {
            "aliases": ["version"],
            "nargs": "?",
            "default": "",
            "help": "Odoo version to update",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

    def run(self):
        config = ConfigManager("odev")
        odoo_path = config.get("paths", "odoo")
        odoo_version = get_worktree_list(odoo_path + ODOO_MASTER_REPO)

        if self.args.version:
            try:
                version = odoo.get_odoo_version(self.args.version)
            except InvalidVersion as exc:
                raise InvalidArgument(str(exc)) from exc

            odoo_version = [p for p in odoo_version if version == p]

        for version in odoo_version:
            version = version_from_branch(version)

            prepare_odoobin(odoo_path, version, venv=False, upgrade=False, skip_prompt=self.args.force)
