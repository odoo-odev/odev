import re
import shlex
from abc import ABC
from argparse import Namespace
from pathlib import Path
from typing import (
    List,
    Literal,
    Mapping,
    Optional,
    Union,
)

from rich import markup

from odev.common import args, string
from odev.common.commands import LocalDatabaseCommand
from odev.common.connectors import GitConnector
from odev.common.databases import LocalDatabase
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess
from odev.common.python import PythonEnv
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


TEMPLATE_SUFFIX = ":template"


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
    version_argument = args.String(
        name="version",
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
    worktree_argument = args.String(
        name="worktree",
        aliases=["-w", "--worktree"],
        description="""Name of the worktree to use when running this database.
        If not specified, defaults to the common worktree for the current Odoo version.
        """,
    )
    pretty = args.Flag(
        aliases=["--no-pretty"],
        description="Do not pretty print the output of odoo-bin but rather display logs as output by the subprocess.",
        default=True,
    )

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------

    ODOO_LOG_REGEX: re.Pattern = re.compile(
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

    ODOO_LOG_WERKZEUG_REGEX: re.Pattern = re.compile(
        r"""
            (?:
                (?P<ip>(?:\d{1,3}\.){3}\d{1,3}).+?\]\s\"
                (?P<verb>\w+)\s
                (?P<url>.+?(?=\s))\s
                (?P<http>.+?(?=\"))\"\s
                (?P<code>\d+)\s-\s
                (?P<count_query>\d+)\s
                (?P<time_query>[\d\.]+)\s
                (?P<time_remaining>[\d\.]+)
            )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    """Regular expression to match the output of odoo-bin Werkzeug-specific logs."""

    last_level: str = "INFO"
    """Log-level level of the last line printed by the odoo-bin process."""

    def __init__(self, args: Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self._set_odoobin_process(
            force=any([self.args.version, self.args.venv, self.args.worktree, self.args.enterprise])
        )

    @property
    def odoobin(self) -> Optional[OdoobinProcess]:
        """The odoo-bin process associated with the database."""
        return self._database.process

    @property
    def version(self) -> OdooVersion:
        """The Odoo version associated with the odoo-bin process."""
        if self.args.version:
            return OdooVersion(self.args.version)

        if self._database.version:
            return self._database.version

        return OdooVersion("master")

    @property
    def venv(self) -> PythonEnv:
        """The Python virtual environment associated with the odoo-bin process."""
        if self.args.venv:
            return PythonEnv(self.args.venv)

        if not self._database.venv._global:
            return self._database.venv

        return PythonEnv(str(self.version))

    @property
    def worktree(self) -> str:
        """The Git worktree associated with the odoo-bin process."""
        if self.args.worktree:
            return self.args.worktree

        if self._database.worktree:
            return self._database.worktree

        if self.args.version:
            return str(OdooVersion(self.args.version))

        return str(self._database.version or "master")

    def odoobin_progress(self, line: str):
        """Beautify odoo logs on the fly."""
        match = self._parse_progress_log_line(line)

        if match is None or not self.args.pretty:
            return self.print(markup.escape(line), highlight=False, soft_wrap=False)

        self.last_level = match.group("level").lower()
        self._print_progress_log_line(match)

    def _guess_addons_paths(self) -> List[Path]:
        """Guess the addons path."""
        if self.args.addons is not None:
            addons_paths = [Path(addon).resolve() for addon in self.args.addons]
            invalid_paths = [path for path in addons_paths if not self.odoobin.check_addons_path(path)]

            if invalid_paths:
                logger.warning(
                    "Some additional addons paths are invalid, they will be ignored:\n"
                    + string.join_bullet([path.as_posix() for path in invalid_paths])
                )
        elif self._database.repository:
            addons_paths = [GitConnector(self._database.repository.full_name).path.resolve()]
        else:
            current_path = Path().resolve()
            addons_paths = [current_path] if self.odoobin.check_addons_path(current_path) else []

        return addons_paths

    def _set_addons_paths(self) -> None:
        """Find additional addons paths from the database repository if any."""
        addons_paths = self._guess_addons_paths()

        globs = [path.glob(f"**/__{manifest}__.py") for path in addons_paths for manifest in ["manifest", "openerp"]]
        addons_paths = [
            path.parents[1] for path in (p for g in globs for p in g) if self.odoobin.check_addons_path(path.parents[1])
        ]

        self.odoobin.additional_addons_paths = sorted(set(addons_paths))
        self.odoobin.save_database_repository()

    def _set_odoobin_process(self, force=False) -> None:
        """Set the odoo-bin process associated with the database.

        :param force: If True, force the creation of a new odoo-bin process even if one already exists.
        """
        if not isinstance(self._database, LocalDatabase):
            raise self.error(f"Database must be an instance of {LocalDatabase.__name__}.")

        if self._database.process is not None and not force:
            return

        version = OdooVersion(self.args.version) if self.args.version else self.version
        venv = PythonEnv(self.args.venv) if self.args.venv else self.venv
        worktree = self.args.worktree or self.worktree
        edition: Literal["community", "enterprise"] = (
            "enterprise" if self.args.enterprise or self._database.edition == "enterprise" else "community"
        )
        process = OdoobinProcess(
            database=self._database,
            version=version,
            venv=venv.name,
            worktree=worktree,
        ).with_edition(edition)
        self._database.process = process
        self._set_addons_paths()

    def _print_progress_log_line(self, match: re.Match):
        """Print a line of odoo-bin output when streamed through the odoobin_progress handler."""
        level_color = "bold color.green" if self.last_level == "info" else f"logging.level.{self.last_level}"
        logger = match.group("logger")
        description = match.group("description")

        if logger == "werkzeug" and (http_match := re.match(self.ODOO_LOG_WERKZEUG_REGEX, description)):
            dash = string.stylize("-", "color.black")
            code = http_match.group("code")

            match code[0]:
                case "4":
                    code = string.stylize(code, "color.yellow")
                case "5":
                    code = string.stylize(code, "color.red")
                case _:
                    code = string.stylize(code, "color.black")

            time_query_num = float(http_match.group("time_query"))
            time_python_num = float(http_match.group("time_remaining"))
            time_total_num = time_query_num + time_python_num

            thresholds = {0.3: "color.yellow", 1.0: "color.red"}
            time_total = self._colorize_duration_by_threshold(time_total_num, thresholds)

            thresholds = {key: f"{value} dim" for key, value in thresholds.items()}
            time_query = self._colorize_duration_by_threshold(time_query_num, thresholds)
            time_python = self._colorize_duration_by_threshold(time_python_num, thresholds)

            description = (
                f"{string.stylize(http_match.group('ip'), 'color.black')} {dash} "
                f"{http_match.group('verb')} {http_match.group('url')} ({code}) {dash} "
                f"{time_total} "
                + string.stylize(
                    f"[SQL: {time_query} ({http_match.group('count_query')} queries), Python: {time_python}]",
                    "color.black",
                )
            )

        self.print(
            f"{string.stylize(match.group('time'), 'color.black')} "
            f"{string.stylize(match.group('level'), level_color)} "
            f"{string.stylize(match.group('database'), 'color.purple')} "
            f"{string.stylize(logger, 'color.black')}: {description}",
            highlight=False,
            soft_wrap=True,
        )

    def _parse_progress_log_line(self, line: str) -> Optional[re.Match]:
        """Parse a line of odoo-bin output."""
        return re.match(self.ODOO_LOG_REGEX, string.strip_ansi_colors(line))

    def _colorize_duration_by_threshold(self, time: Union[str, float], thresholds: Mapping[float, str]) -> str:
        """Colorize the textual representation of a duration according to thresholds.
        :param time: The duration to colorize.
        :param thresholds: A list of tuples containing a threshold and a color.
        :return: The colorized duration.

        Example:
        >>> self._colorize_duration_by_threshold(
        >>>     time=2.51,
        >>>     thresholds={
        >>>         0.0: "color.green",
        >>>         0.3: "color.yellow",
        >>>         1.0: "color.red",
        >>>     },
        >>> )
        "[color.red]2.510[/color.red]"
        """
        time = float(time)
        style = thresholds.get(max(filter(lambda x: x < time, thresholds.keys()), default=0.0))
        return string.stylize(f"{time:.3f}", style) if style else f"{time:.3f}"


class OdoobinTemplateCommand(OdoobinCommand):
    """Handle template databases through command line arguments."""

    from_template = args.String(
        aliases=["-t", "--from-template"],
        description="Name of an existing PostgreSQL database to copy.",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.infer_template_instance()

    def infer_template_instance(self):
        """Infer the template database from the command line arguments."""
        if self.args.from_template:
            self._template = LocalDatabase(self.args.from_template)

            if not self._template.exists and not self._template.name.endswith(TEMPLATE_SUFFIX):
                self._template = LocalDatabase(self.args.from_template + TEMPLATE_SUFFIX)
        elif self.args.from_template is not None:
            template_name = self._database.name + TEMPLATE_SUFFIX
            self._template = LocalDatabase(template_name)
        else:
            self._template = None

        if self._template and not self._template.exists:
            raise self.error(f"Template database {self._template.name!r} does not exist")


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
