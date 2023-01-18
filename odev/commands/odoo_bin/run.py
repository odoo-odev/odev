"""Runs a local Odoo database."""
import random
import time
from collections import namedtuple
from typing import List

from odev.commands.odoo_db import create, remove
from odev.constants import DB_TEMPLATE_SUFFIX, UNCLEAN_DB_WARNING_MSG
from odev.exceptions import CommandAborted, RunningOdooDatabase
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class RunCommand(commands.TemplateDBCommand, commands.OdooBinMixin):
    """
    Run a local Odoo database, prefilling common addon paths and making
    sure the right version of Odoo is installed and in use.

    If the version of Odoo required for the database is not present, download and install it locally.
    This is done by cloning the Odoo community, enterprise and design-themes repositories
    multiple times (once per version) to always keep a copy of each version on the computer.
    To save storage space, only one branch is cloned per version, keeping all other branches out of
    the history.
    """

    name = "run"

    arguments = [
        {
            "aliases": ["-fv", "--force-version"],
            "type": str,
            "dest": "force_version",
            "metavar": "VERSION",
            "help": """
            Force running a specific Odoo version for the database.
            Can be useful to manually run an upgrade to a newer Odoo version.
            If not specified, the Odoo version to run is obtained from the database.
            """,
        },
    ]

    use_config_args = True

    def run(self):
        """
        Runs a local Odoo database.
        """

        if self.args.from_template:
            template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"
            self.check_database(template_db_name)

            if self.db_exists(self.database):
                _logger.info("The old database will be deleted to restore the template")
                remove.RemoveCommand.run_with(**dict(self.args.__dict__, keep_template=bool(self.args.from_template)))

            _logger.warning(f"Restoring the template {template_db_name}")
            create.CreateCommand.run_with(**dict(self.args.__dict__, template=template_db_name))

        self.check_database()

        if self.db_runs() and self.name == "run":
            raise RunningOdooDatabase(f"Database {self.database} is already running")

        if not self.db_is_neutralized():
            self.print_ominous_uncleandb_warning_message()

        if not self.addons:
            _logger.warning(
                "No additional addons specified. "
                "Will try adding the current directory, otherwise will run as enterprise",
            )

        self.run_odoo(
            subcommand=self.odoobin_subcommand,
            additional_args=self.additional_args,
            venv_name=self.args.alt_venv and self.args.database,
            check_last_run=True,
            version=self.args.force_version,
        )

        return 0

    @staticmethod
    def print_ominous_uncleandb_warning_message():
        if not logging.interactive:
            raise RuntimeError("Cannot run an unclean database with odev in non-interactive mode")
        delay_base: float = 0.01
        lines: List[str] = UNCLEAN_DB_WARNING_MSG.split("\n")
        max_rows: int = len(lines)
        max_cols: int = max(len(line) for line in lines)
        if logging.term.does_styling and max_cols < logging.term.width:
            Pixel = namedtuple("Pixel", ["char", "row", "col"])
            print("\n" * (max_rows + 1) + logging.term.move_up(max_rows), end="")
            for char, color, delay in (
                (" ", logging.term.red, 0 * delay_base),
                ("▀█▄▐▌", logging.term.orangered, 1 * delay_base),
                ("▓", logging.term.red, 3 * delay_base),
                ("▒", logging.term.red3, 5 * delay_base),
                ("░", logging.term.darkred, 10 * delay_base),
            ):
                pixels: List[Pixel] = [
                    Pixel(c, row, col) for row, line in enumerate(lines) for col, c in enumerate(line) if c in char
                ]
                random.shuffle(pixels)
                for c, row, col in pixels:
                    print(logging.term.move_down(row) + logging.term.move_x(col) + color + c, end="")
                    print(logging.term.move_up(row) + logging.term.move_x(0), end="", flush=True)
                    time.sleep(delay / max_rows)
            print(logging.term.normal + logging.term.move_down(max_rows) + logging.term.move_x(0))

        _logger.warning(
            (logging.term.bold + logging.term.orangered)
            + (
                "WARNING!!! Running a non-neutralized database!\n"
                "If this database is a dump from production, "
                "it will communicate with the external world and lead to unintended consequences!\n"
                "If you are not sure what this means, stop this process now with CTRL-C and run `odev clean` first"
            )
            + logging.term.normal
        )
        if not _logger.confirm(
            (logging.term.bold + logging.term.orangered)
            + "Confirm you have read the above warning, understand the risks, and want to continue"
            + logging.term.normal
        ):
            raise CommandAborted()
