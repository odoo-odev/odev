import re
import shlex
from abc import ABC
from argparse import Namespace
from pathlib import Path
from typing import Optional

from odev.common import string
from odev.common.commands import LocalDatabaseCommand
from odev.common.console import RICH_THEME_LOGGING, Colors
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class OdoobinCommand(LocalDatabaseCommand, ABC):
    """Base class for commands that interact with an odoo-bin process."""

    arguments = [
        {
            "name": "addons",
            "nargs": "?",
            "action": "store_comma_split",
            "help": """Comma-separated list of additional addon paths.
            The standard Odoo addons paths are automatically added to the odoo-bin command (including enterprise
            if any enterprise module is installed). If this command is run from within an Odoo addons directory
            and no additional addons are specified, the current directory will be added to the list of addons.
            """,
        },
        {
            "name": "odoo_args",
            "nargs": "*...",
            "help": """Additional arguments to pass to odoo-bin; Check the documentation at
            https://www.odoo.com/documentation/17.0/fr/developer/cli.html
            for the list of available arguments.
            """,
        },
        {
            "name": "enterprise",
            "aliases": ["-e", "--enterprise"],
            "action": "store_true",
            "help": "Force running the database with enterprise addons.",
        },
        {
            "name": "version",
            "aliases": ["-V", "--version"],
            "help": """The Odoo version to use for running the database.
            If not specified, defaults to the latest version of the base module installed in the database.
            """,
        },
    ]

    _odoo_log_regex: re.Pattern = re.compile(
        r"""
            (?:
                (?P<date>\d{4}-\d{2}-\d{2})\s
                (?P<time>\d{2}:\d{2}:\d{2},\d{3})\s
                (?P<pid>\d+)\s
                (?P<level>[A-Z]+)\s
                (?P<database>[^\s]+)\s
                (?P<logger>
                    ((?:odoo\.addons\.)(?P<module>[^\.]+))?[^:]+
                ):\s
                (?P<description>.*)
            )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    """Regular expression to match the output of odoo-bin."""

    last_level: str = None
    """Log-level level of the last line printed by the odoo-bin process."""

    def __init__(self, args: Namespace, **kwargs):
        super().__init__(args, **kwargs)
        if not isinstance(self.database, LocalDatabase):
            raise self.error(f"Database must be an instance of {LocalDatabase.__name__}.")

        if self.args.addons is not None:
            addons_paths = [Path(addon).resolve() for addon in self.args.addons]
            invalid_paths = [path for path in addons_paths if not self.odoobin.check_addons_path(path)]

            if invalid_paths:
                logger.warning(
                    "Some additional addons paths are invalid, they will be ignored:\n"
                    + "\n".join(path.as_posix() for path in invalid_paths)
                )
        else:
            addons_paths = [Path().resolve()]

        if self.odoobin is not None:
            self.odoobin.additional_addons_paths = addons_paths
            self.odoobin._force_enterprise = bool(self.args.enterprise)

            if self.args.version is not None:
                self.odoobin._version = OdooVersion(self.args.version)

    @property
    def odoobin(self) -> Optional[OdoobinProcess]:
        """The odoo-bin process associated with the database."""
        return self.database.process

    def odoobin_progress(self, line: str):
        """Beautify odoo logs on the fly."""
        match = re.match(self._odoo_log_regex, line)

        if match is None:
            color = (
                RICH_THEME_LOGGING[f"logging.level.{self.last_level}"]
                if self.last_level in ("warning", "error", "critical")
                else Colors.BLACK
            )
            return self.print(string.stylize(line, color), highlight=False)

        self.last_level = match.group("level").lower()
        level_color = (
            f"bold {Colors.GREEN}"
            if self.last_level == "info"
            else RICH_THEME_LOGGING[f"logging.level.{self.last_level}"]
        )

        self.print(
            f"{string.stylize(match.group('time'), Colors.BLACK)} "
            f"{string.stylize(match.group('level'), level_color)} "
            f"{string.stylize(match.group('database'), Colors.PURPLE)} "
            f"{string.stylize(match.group('logger'), Colors.BLACK)}: {match.group('description')}",
            highlight=False,
        )


class OdoobinShellCommand(OdoobinCommand, ABC):
    """Base class for commands that interact with an odoo-bin shell process
    with the added ability to run scripts inside its environment."""

    arguments = [
        {
            "name": "script",
            "aliases": ["--script"],
            "help": """
            Run a script inside of odoo-bin shell and exit. Can be a path
            to a file containing python code or a string representing
            python code to be executed inside the shell environment.
            """,
        },
    ]

    @property
    def script_run_after(self) -> str:
        """The python code to be executed inside the shell environment after the script
        has been loaded. May be used to call the script function if the script is a file.
        """
        return ""

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if self.args.script:
            result = self.run_script()

            if result is not None:
                return self.run_script_handle_result(result)

        else:
            self.odoobin.run(args=self.args.odoo_args, subcommand="shell")

    def run_script(self) -> Optional[str]:
        """Run a script inside of odoo-bin shell and exit.
        :return: The output of the script.
        """
        if Path(self.args.script).is_file():
            subcommand_input = f"cat {self.args.script}"
        else:
            subcommand_input = f"echo {shlex.quote(self.args.script)}"

        if self.script_run_after:
            run_after: str = self.script_run_after

            if not run_after.startswith("print("):
                run_after = f"print({self.script_run_after})"

            subcommand_input = f"{subcommand_input}; echo {shlex.quote(run_after)}"

        process = self.odoobin.run(
            args=self.args.odoo_args,
            subcommand="shell",
            subcommand_input=f"{{ {subcommand_input}; }}",
            stream=False,
        )

        if process is None or process.stdout is None:
            return None

        return process.stdout.decode()

    def run_script_handle_result(self, result: str):
        """Handle the result of the script execution.
        This is designed to be overridden by subclasses.
        By default, prints to result to the console.
        """
        logger.info(result.strip())


class OdoobinShellScriptCommand(OdoobinShellCommand, ABC):
    """Base class for commands that interact with an odoo-bin shell process
    by running a predefined script inside its environment.
    """

    def __init__(self, args: Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self.args.script = (self.odev.scripts_path / f"{self.name}.py").as_posix()

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        cls.remove_argument("script")
