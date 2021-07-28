"""Quickly and easily setups a database from a version no., dump or url."""

import logging
import os
import re
import shutil
from argparse import ArgumentParser, Namespace
from datetime import datetime

from .clean import CleanScript
from .create import CreateScript
from .database import LocalDBCommand
from .dump import DumpScript
from .init import InitScript
from .remove import RemoveScript
from .restore import RestoreScript


_logger = logging.getLogger(__name__)


re_version = re.compile(r"^([a-z~0-9]+\.[0-9]+)")
re_url = re.compile(
    r"^https?://|(?:[a-zA-Z0-9-_](?:\.dev)?\.odoo\.com|localhost|127\.0\.0\.[0-9]+)"
)


class QuickStartScript(LocalDBCommand):
    command = "quickstart"
    aliases = ("qs",)
    help = """
        Quickly and easlily setups a database. This performs the following actions:
        - Creates a new, empty database
        - Initializes, dumps and restores or restores an existing dump to the new database
        - Cleanses the database so that it can be used for development
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            dest="something",
            metavar="VERSION|PATH|URL",
            help="One of the following:"
            "- a <version> to create and init an empty database\n"
            "- the <path> of a local dump file to restore to a new database "
            "(the file must be a valid database dump)\n"
            "- an <url> of a Odoo SaaS or SH database to dump and restore locally",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.subarg = args.something

    def run(self):
        """
        Creates, initializes or restores and cleanses a local database.
        """
        if re_version.match(self.subarg):
            mode = "version"
        elif re_url.match(self.subarg):
            mode = "url"
        else:
            mode = "file"

        result = CreateScript.run_with(database=self.database, template=None)
        if result != 0:
            return result

        try:
            if mode == "version":
                result = InitScript.run_with(database=self.database, version=self.subarg)
            else:
                if mode == "url":
                    dest_dir = "/tmp/odev"

                    result = DumpScript.run_with(
                        url=self.subarg,
                        destination=dest_dir,
                        database=self.database,
                    )
                    if result != 0:
                        return result

                    timestamp = datetime.now().strftime("%Y%m%d")
                    basename = f"{timestamp}_{self.database}.dump"

                    possible_ext = ("zip", "dump", "sql")
                    for ext in possible_ext:
                        filename = os.path.extsep.join((basename, ext))
                        filepath = os.path.join(dest_dir, filename)
                        if os.path.isfile(filepath):
                            break
                    else:
                        raise Exception(
                            f"An error occured while fetching dump file at {basename}.<ext> "
                            f"(tried {possible_ext} extensions)"
                        )

                else:
                    filepath = self.subarg

                result = RestoreScript.run_with(database=self.database, dump=filepath)
                if result != 0:
                    return result

                result = CleanScript.run_with(database=self.database)

        except Exception as exception:
            _logger.error("An error occured, cleaning up files and removing database:")
            _logger.error(str(exception))
            RemoveScript.run_with(database=self.database)
            result = 1

        finally:
            if os.path.isdir("/tmp/odev"):
                shutil.rmtree("/tmp/odev")

        return result
