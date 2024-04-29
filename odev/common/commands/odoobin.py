import re
import shlex
from abc import ABC
from argparse import Namespace
from pathlib import Path
from typing import Optional

from odev.common import args, string
from odev.common.commands import LocalDatabaseCommand
from odev.common.console import RICH_THEME_LOGGING, Colors
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess
from odev.common.python import PythonEnv
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class OdoobinCommand(LocalDatabaseCommand, ABC):
    """Base class for commands that interact with an odoo-bin process."""

    # --------------------------------------------------------------------------
    # Arguments
    # --------------------------------------------------------------------------

    addons = args.List(
        nargs="?",
        description="""Comma-separated list of additional addon paths.
        The standard Odoo addons paths are automatically added to the odoo-bin command (including enterprise
        if any enterprise module is installed). If this command is run from within an Odoo addons directory
        and no additional addons are specified, the current directory will be added to the list of addons.
        """,
    )
    odoo_args = args.String(
        nargs="*...",
        description="""Additional arguments to pass to odoo-bin; Check the documentation at
        https://www.odoo.com/documentation/17.0/fr/developer/cli.html
        for the list of available arguments.
        """,
    )
    enterprise = args.Flag(
        aliases=["-c", "--community"],
        description="Force running the database without enterprise addons.",
        default=True,
    )
    version = args.String(
        aliases=["-V", "--version"],
        description="""The Odoo version to use for running the database.
        If not specified, defaults to the latest version of the base module installed in the database.
        """,
    )
    venv_argument = args.String(
        name="venv",
        aliases=["--venv"],
        description="""Name of the Python virtual environment to use when running this database.
        If not specified, defaults to the common virtual environment for the current Odoo version.
        """,
    )

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------

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

    last_level: str = "INFO"
    """Log-level level of the last line printed by the odoo-bin process."""

    def __init__(self, args: Namespace, **kwargs):
        super().__init__(args, **kwargs)
        if not isinstance(self._database, LocalDatabase):
            raise self.error(f"Database must be an instance of {LocalDatabase.__name__}.")

        if self.odoobin is not None:
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

            self.odoobin.additional_addons_paths = addons_paths
            self.odoobin.with_edition("enterprise" if self.args.enterprise else "community")

            if self.args.version is not None:
                self.odoobin.with_version(OdooVersion(self.args.version))

            self.odoobin.with_venv(self.venv.name)

    @property
    def odoobin(self) -> Optional[OdoobinProcess]:
        """The odoo-bin process associated with the database."""
        return self._database.process

    @property
    def venv(self) -> PythonEnv:
        """The Python virtual environment associated with the odoo-bin process."""
        if self.args.venv:
            return PythonEnv(self.args.venv)

        if not self._database.venv._global:
            return self._database.venv

        if self.args.version:
            return PythonEnv(str(OdooVersion(self.args.version)))

        return PythonEnv(str(self._database.version))

    def odoobin_progress(self, line: str):
        """Beautify odoo logs on the fly."""
        match = re.match(self._odoo_log_regex, re.sub(r"\x1b[^m]*m", "", line))

        if match is None:
            return self.print(line, highlight=False, soft_wrap=True)

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
            soft_wrap=True,
        )


class OdoobinShellCommand(OdoobinCommand, ABC):
    """Base class for commands that interact with an odoo-bin shell process
    with the added ability to run scripts inside its environment."""

    script = args.String(
        aliases=["--script"],
        description="""
        Run a script inside of odoo-bin shell and exit. Can be a path
        to a file containing python code or a string representing
        python code to be executed inside the shell environment.
        """,
    )

    @property
    def script_run_after(self) -> str:
        """The python code to be executed inside the shell environment after the script
        has been loaded. May be used to call the script function if the script is a file.
        """
        return ""

    def run(self):
        """Run the odoo-bin process for the selected database locally."""
        if self.odoobin is None:
            raise self.error(f"No odoo-bin process could be instantiated for database {self._database!r}")

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
        if self.odoobin is None:
            raise self.error(f"No odoo-bin process could be instantiated for database {self._database!r}")

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
        self.args.script = (self.odev.scripts_path / f"{self!s}.py").as_posix()

    @classmethod
    def prepare_command(cls, *args, **kwargs) -> None:
        super().prepare_command(*args, **kwargs)
        cls.remove_argument("script")
