"""Quickly and easily setups a database from a version no., dump or url."""

import os
import re
from argparse import Namespace
from datetime import datetime

from odev.commands.exporter import scaffold
from odev.commands.github import clone
from odev.commands.odoo_db import (
    create,
    dump,
    init,
    remove,
    restore,
)
from odev.exceptions import InvalidVersion
from odev.structures import commands, database
from odev.utils import logging
from odev.utils.odoo import get_odoo_version


_logger = logging.getLogger(__name__)


re_url = re.compile(r"^https?:\/\/|(?:[a-zA-Z0-9-_]+(?:\.dev)?\.odoo\.(com|sh)|localhost|127\.0\.0\.[0-9]+)")

TMP_DIR = "/tmp/odev"


class QuickStartCommand(
    database.DBExistsCommandMixin, commands.OdooComCliMixin, commands.OdooBinMixin, commands.ExportCommand
):
    """
    Quickly setup a local database and start working with it directly.

    This command performs the following actions:
      - Create a new, empty database
      - Initialize, dump and restore or restore an existing dump
      - Clean the database so that it can be used for development
    """

    name = "quickstart"
    aliases = ["qs"]

    arguments = [
        {
            "aliases": ["source"],
            "metavar": "VERSION|PATH|URL",
            "help": """
            One of the following:
                - an Odoo version number to create and init an empty database
                - a path to a local dump file to restore to a new database
                - a url to an Odoo SaaS or SH database to dump and restore locally
            """,
        },
        # move positional args from OdooBinMixin after "source"
        {"name": "addons"},
        {"name": "args"},
        {
            "aliases": ["--id", "--task"],
            "dest": "task_id",
            "help": "Scaffold the code for this task_id",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.subarg = args.source
        self.args.reason = (
            f"Working on {self.args.task_id}" if not self.args.reason and self.args.task_id else self.args.reason
        )

    def run(self):
        """
        Creates, initializes or restores and cleanses a local database.
        """
        try:
            get_odoo_version(self.subarg)
            mode = "version"
        except InvalidVersion:
            mode = "url" if re_url.match(self.subarg) else "file"

        try:
            if mode == "version":
                result = init.InitCommand.run_with(**dict(self.args.__dict__, version=self.subarg))
            else:
                if mode == "url":
                    result = dump.DumpCommand.run_with(
                        **self.args.__dict__,
                        url=self.subarg,
                        destination=TMP_DIR,
                    )
                    if result != 0:
                        return result

                    timestamp = datetime.now().strftime("%Y%m%d")
                    basename = f"{timestamp}_{self.database}.dump"

                    possible_ext = ("zip", "sql.gz")
                    for ext in possible_ext:
                        filename = os.path.extsep.join((basename, ext))
                        filepath = os.path.join(TMP_DIR, filename)
                        if os.path.isfile(filepath):
                            break
                    else:
                        raise Exception(
                            f"An error occurred while fetching dump file at {basename}.<ext> "
                            f"(tried {possible_ext} extensions)"
                        )

                else:  # mode == 'file'
                    filepath = self.subarg

                result = restore.RestoreCommand.run_with(**self.args.__dict__, dump=filepath, no_clean=False)

                if result != 0:
                    return result

        except Exception as exception:
            _logger.error(f"An error occurred : {str(exception)}")
            result = int(self.do_raise)

            if result:
                _logger.error("Cleaning up files and removing database")
                remove.RemoveCommand.run_with(**self.args.__dict__)

        if mode == "url":
            clone.CloneCommand.run_with(**dict(self.args.__dict__, url=self.subarg))

        if self.args.task_id:
            self.args.path = self.globals_context.get("repo_git_path", self.args.path)
            result += scaffold.ScaffoldCommand.run_with(**self.args.__dict__)

        return result
