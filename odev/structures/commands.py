"""Command-line commands base classes and utility functions"""

import inspect
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
from abc import ABC, abstractmethod
from argparse import (
    REMAINDER,
    SUPPRESS,
    ArgumentParser,
    Namespace,
    RawTextHelpFormatter,
)
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    ContextManager,
    Dict,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)

import imgkit
import odoolib
from github import Github
from packaging.version import Version

from odev.commands.utilities.help import HELP_ARGS_ALIASES
from odev.common.actions import CommaSplitAction, OptionalStringAction
from odev.constants import (
    DB_TEMPLATE_SUFFIX,
    DEFAULT_DATABASE,
    DEFAULT_DATETIME_FORMAT,
    DEFAULT_VENV_NAME,
    HELP_ARGS_ALIASES,
    ICON_COLORS,
    ICON_OPTIONS,
    RE_COMMAND,
    RE_PORT,
)
from odev.exceptions import (
    BuildCompleteException,
    BuildFail,
    BuildTimeout,
    BuildWarning,
    CommandAborted,
    InvalidArgument,
    InvalidDatabase,
    InvalidFileArgument,
    InvalidOdooDatabase,
    RunningOdooDatabase,
)
from odev.exceptions.commands import InvalidQuery
from odev.utils import logging, odoo
from odev.utils.config import ConfigManager
from odev.utils.exporter import Config, odoo_field, odoo_model
from odev.utils.github import get_github
from odev.utils.odoo import (
    check_database_name,
    get_odoo_version,
    get_venv_path,
    is_addon_path,
    is_really_module,
    parse_odoo_version,
)
from odev.utils.os import mkdir
from odev.utils.pre_commit import fetch_pre_commit_config
from odev.utils.psql import PSQL
from odev.utils.shconnector import ShConnector, get_sh_connector
from odev.utils.signal import capture_signals
from odev.utils.spinner import SpinnerBar, poll_loop
from odev.utils.template import Template


if TYPE_CHECKING:
    from odev.structures.registry import CommandRegistry


_logger = logging.getLogger(__name__)


CommandType = Type["BaseCommand"]


class BaseCommand(ABC):
    """
    Base class for handling commands.
    """

    name: ClassVar[str]
    """
    The name of the command associated with the class. Must be unique.
    """

    aliases: ClassVar[Sequence[str]] = []
    """
    Additional aliases for the command. These too must be unique.
    """

    subcommands: ClassVar[MutableMapping[str, CommandType]] = {}
    """
    Subcommands' classes available for this command.
    """

    command: ClassVar[Optional[CommandType]] = None
    """
    Parent command class.
    """

    registry: ClassVar[Optional["CommandRegistry"]] = None
    """
    Commands registry for access to sibling commands.
    """

    parent: ClassVar[Optional[str]] = None
    """
    Name of the parent command, for auto linking.
    """

    help: ClassVar[Optional[str]] = None
    """
    Optional help information on what the command does.
    """

    help_short: ClassVar[Optional[str]] = None
    """
    Optional short help information on what the command does.
    If omitted, the class or source module docstring will be used instead.
    """

    arguments: ClassVar[List[MutableMapping[str, Any]]] = []
    """
    Arguments definitions to extend commands capabilities.
    """

    is_abstract: ClassVar[bool] = False

    def __init__(self, args: Namespace):
        """
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        """
        self.args: Namespace = args
        self.argv: Optional[Sequence[str]] = None

    @classmethod
    def prepare(cls):
        """
        Set proper name and help descriptions attributes.
        Also implement inheriting arguments from parent classes.
        """
        cls.name = (cls.name or cls.__name__).lower()
        cls.is_abstract = inspect.isabstract(cls) or ABC in cls.__bases__
        cls.help = textwrap.dedent(
            cls.__dict__.get("help") or cls.__doc__ or cls.help or sys.modules[cls.__module__].__doc__ or ""
        ).strip()
        cls.help_short = textwrap.dedent(cls.help_short or cls.help).strip()

        cls.arguments = cls._get_merged_arguments()

    @classmethod
    def _get_merged_arguments(cls) -> List[Dict[str, Any]]:
        merged_arguments: MutableMapping[str, Dict[str, Any]] = {}
        cls_: Type
        for cls_ in reversed(cls.mro()):
            argument: MutableMapping[str, Any]
            for argument in getattr(cls_, "arguments", []):
                argument_name: Optional[str] = argument.get(
                    "name", argument.get("dest", argument.get("aliases", [None])[0])
                )
                if not argument_name:
                    raise ValueError(
                        f"Missing name for argument {argument}, "
                        "please provide at least one of `name`, `dest` or `aliases`"
                    )
                merged_argument: Dict[str, Any]
                # pop existing argument to preserve order of current class
                merged_argument = dict(merged_arguments.pop(argument_name, {}))
                merged_argument.update(argument)
                merged_argument.setdefault("name", argument_name)
                aliases: Union[str, List[str]] = merged_argument.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = [aliases]
                if argument_name not in aliases:
                    if not aliases or not aliases[0].startswith("-"):
                        aliases = [argument_name] + aliases
                merged_argument["aliases"] = aliases

                merged_arguments[argument_name] = merged_argument

        return list(merged_arguments.values())

    @classmethod
    def prepare_parser(cls) -> ArgumentParser:
        """
        Prepares the argument parser for the :class:`CliCommand` class.

        :return: a instance of :class:`ArgumentParser` prepared with all the arguments
            defined in the command an in its parent's classes.
        """
        parser: ArgumentParser = ArgumentParser(
            prog=cls.name,
            description=cls.help,
            formatter_class=RawTextHelpFormatter,
            add_help=False,
        )
        cls.prepare_arguments(parser)

        return parser

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        """
        Prepares the argument parser for the :class:`Command` subclass.
        """
        for argument in cls.arguments:
            params = dict(argument)
            params.pop("name")
            aliases = params.pop("aliases")

            parser.add_argument(*aliases, **params)

    @classmethod
    def run_with(cls, do_raise: bool = True, capture_output: bool = False, **kwargs) -> int:
        """
        Runs the command directly with the provided arguments, bypassing parsers
        """
        parser: ArgumentParser = cls.prepare_parser()
        default_args: MutableMapping[str, Any] = dict(
            parser._defaults,
            **{
                action.dest: action.default
                for action in parser._actions
                if action.dest is not SUPPRESS and action.default is not SUPPRESS
            },
        )
        args: MutableMapping[str, Any] = dict(
            {**default_args, **kwargs}, do_raise=do_raise, capture_output=capture_output
        )

        res = cls(Namespace(**args)).run()

        if not do_raise and res:
            res = 0
        return res

    @abstractmethod
    def run(self) -> int:
        """
        The actual script to run when calling the command.
        """
        raise NotImplementedError()

    def get_arg(self, name, default=None):
        return getattr(self.args, name, default)


class Command(BaseCommand, ABC):
    """
    Basic command to run from the terminal.
    """

    config: Dict[str, ConfigManager] = {}
    """
    General configuration for odev and databases.
    """

    do_raise: bool = True
    """
    Raise errors unless explicitly disabled through `run_with()` with `do_raise=False`
    """

    capture_output: bool = False
    """
    If True, return the output of commands executed through `run_with()`.
    """

    _globals_context: ClassVar[MutableMapping[str, Any]] = {}

    arguments: ClassVar[List[MutableMapping[str, Any]]] = [
        {
            "aliases": ["-y", "--yes"],
            "dest": "assume_yes",
            "action": "store_true",
            "help": "Assume `yes` as answer to all prompts and run non-interactively",
        },
        {
            "aliases": ["-n", "--no"],
            "dest": "assume_no",
            "action": "store_true",
            "help": "Assume `no` as answer to all prompts and run non-interactively",
        },
        {
            "aliases": ["-v", "--log-level"],
            "choices": ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
            "default": "INFO",
            "help": "Set logging verbosity",
        },
        {
            "aliases": HELP_ARGS_ALIASES,
            "dest": "show_help",
            "action": "store_true",
            "help": "Show help for the current command.",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        if args.assume_yes and args.assume_no:
            raise InvalidArgument("Arguments `assume_yes` and `assume_no` cannot be used together")

        logging.interactive = not (args.assume_yes or args.assume_no)
        logging.assume_yes = args.assume_yes or not args.assume_no
        logging.set_log_level(args.log_level)

        self.do_raise = "do_raise" not in args or args.do_raise

        self.capture_output = "capture_output" in args and args.capture_output

        if not logging.interactive and not logging.assume_prompted:
            _logger.info(f"""Assuming '{'yes' if logging.assume_yes else 'no'}' for all confirmation prompts""")
            logging.assume_prompted = True

        for key in ["odev"]:
            self.config[key] = ConfigManager(key)

    @property
    def globals_context(self) -> MutableMapping[str, Any]:
        return self.__class__._globals_context


class LocalDatabaseCommand(Command, ABC):
    """
    Command class for interacting with local databases through the terminal.
    """

    database_required = True
    """
    Whether a database is required when running this command or not.
    """

    add_database_argument = True
    """
    If set to `False`, no default `database` argument will be added.
    """

    database: str
    """
    Name of a local database on which to perform operations.
    """

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        if cls.add_database_argument and not any(a.get("name") == "database" for a in cls.arguments):
            parser.add_argument(
                "database",
                action=OptionalStringAction,
                nargs=1 if cls.database_required else "?",
                help="Name of the local database to target",
            )
        super().prepare_arguments(parser)

    def __init__(self, args: Namespace):
        super().__init__(args)

        for key in ["databases"]:
            self.config[key] = ConfigManager(key)

        self.database_required = self.database_required and self.add_database_argument
        self.database = self.database_required and self._get_database(database=args.database) or ""
        self._clean_old_db()

    def remove(
        self, database: str = None, keep_template: bool = False, keep_filestore: bool = False, keep_venv: bool = False
    ):
        """
        Deletes an existing local database and its filestore.
        """
        self.database = database or self.database

        if not self.db_exists_all():
            if _logger.confirm(f"Database {self.database} does not exist, do you still want to delete its filestore?"):
                self.remove_filestore()
                self.remove_configuration()
                return 0
            raise InvalidDatabase(f"Database {self.database} does not exist")

        if self.db_runs():
            raise RunningOdooDatabase(f"Database {self.database} is running, please shut it down and retry")

        is_odoo_db = self.is_odoo_db()
        version = is_odoo_db and self.db_version_clean()

        dbs = [self.database]
        queries = [f"""DROP DATABASE "{self.database}";"""]
        info_text = f"Dropping PSQL database {self.database}"
        template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"

        if not keep_template and self.db_exists(template_db_name):
            _logger.warning(f"You are about to delete the database template {template_db_name}")

            confirm = _logger.confirm(f"Delete database template `{template_db_name}` ?")
            if confirm:
                queries.append(f"""DROP DATABASE "{template_db_name}";""")
                dbs.append(template_db_name)
                info_text += " and his template"

        with_filestore = " and its filestore" if not keep_filestore else ""

        _logger.warning(
            f"You are about to delete the database {self.database}{with_filestore}. This action is irreversible."
        )

        if not is_odoo_db:
            _logger.warning(f"Warning: {self.database} is not an Odoo database.")

        if not _logger.confirm(f"Delete database {self.database}{with_filestore}?"):
            raise CommandAborted()

        _logger.info(info_text)
        # We need two calls as Postgres will embed those two queries inside a block
        # https://github.com/psycopg/psycopg2/issues/1201
        result = None

        for query in queries:
            result = self.run_queries(query, database=DEFAULT_DATABASE)

        if not result or self.db_exists_all():
            return 1

        _logger.debug(f"Dropped database {self.database}{with_filestore}")

        if not keep_filestore:
            self.remove_filestore()

        if is_odoo_db and not keep_venv:
            self.remove_specific_venv(version)

        self.remove_configuration(dbs)

        return 0

    def remove_configuration(self, databases=None):
        for db in databases or [self.database]:
            if db in self.config["databases"]:
                self.config["databases"].delete(db)

    def remove_filestore(self):
        filestore = self.db_filestore()
        if not os.path.exists(filestore):
            _logger.info("Filestore not found, no action taken")
        else:
            try:
                _logger.info(f"Deleting filestore in `{filestore}`")
                shutil.rmtree(filestore)
            except Exception as exc:
                _logger.warning(f"Error while deleting filestore: {exc}")

    def remove_specific_venv(self, version: str):
        venv_path: str = get_venv_path(self.config["odev"].get("paths", "odoo"), version, self.database)
        assert not venv_path.endswith(DEFAULT_VENV_NAME)
        if os.path.isdir(venv_path):
            try:
                _logger.info(f"Deleting database-specific venv in `{venv_path}`")
                shutil.rmtree(venv_path)
            except Exception as exc:
                _logger.warning(f"Error while deleting database-specific venv: {exc}")

    def _clean_old_db(self):
        config = ConfigManager("odev")

        default_date = (datetime.today() - timedelta(days=6)).strftime(DEFAULT_DATETIME_FORMAT)
        update_check_interval = config.get("clean", "clean_interval", 10)
        last_update_check = config.get("clean", "last_clean", default_date)
        last_check_diff = (datetime.today() - datetime.strptime(last_update_check, DEFAULT_DATETIME_FORMAT)).days

        if last_check_diff > update_check_interval:
            min_delay_before_drop = int(config.get("cleaning", "min_delay_before_drop"), 10)
            databases_to_clean: List = []

            for db_section in self.config["databases"].values():
                is_neutralized = self.db_is_neutralized(db_section["name"])

                if is_neutralized and db_section.get("whitelist_cleaning") == "true":
                    continue

                last_access = (
                    db_section.get("last_run", db_section.get("create_date"))
                ) or datetime.today().isoformat()
                last_access_date = datetime.fromisoformat(last_access)

                day_since_last_run = (datetime.today() - last_access_date).days

                if day_since_last_run > min_delay_before_drop:
                    databases_to_clean.append(
                        {
                            "config": db_section,
                            "day_since_last_run": day_since_last_run,
                            "is_neutralized": is_neutralized,
                        }
                    )

            if databases_to_clean:
                warn_msg = (
                    f"You have some databases ({len(databases_to_clean)})"
                    f" that where not used for more than {min_delay_before_drop} day(s)."
                )
                _logger.warning(warn_msg)

                if _logger.confirm("Do you want to check them now and delete them?"):
                    for db in databases_to_clean:
                        choice_options = ["y", "n"]
                        if db["is_neutralized"]:
                            choice_options.append("(w)hitelist")
                        answer = _logger.ask(
                            f"The database {db['config'].name} hasn't been used for {db['day_since_last_run']} day(s)."
                            " Can Odev delete it?",
                            default="y",
                            choice_options=choice_options,
                        )

                        if answer == "y":
                            self.remove(db)
                        elif db["is_neutralized"] and answer == "w":
                            self.config["databases"].set(db["config"].name, "whitelist_cleaning", "true")

            config.set("clean", "last_clean", datetime.today().strftime(DEFAULT_DATETIME_FORMAT))

    def _get_database(self, database=None) -> str:
        database = database or self.database or DEFAULT_DATABASE
        check_database_name(database)
        return database

    def run_queries(self, queries=None, database=None, raise_on_error=True):
        """
        Runs queries on the Postgresql instance of a database.
        """
        database = self._get_database(database)
        result = None

        if queries:
            if not isinstance(queries, list):
                queries = [queries]

            with PSQL(database) as psql:
                try:
                    result = psql.query("; ".join(queries))
                except Exception as e:
                    if raise_on_error:
                        raise InvalidQuery(e)
                    return None

            if any(query.lower().startswith("select") for query in queries):
                return result
            else:
                return True

    def db_list(self):
        """
        Lists names of local Odoo databases.
        """
        return self.config["databases"].sections()

    def db_list_all(self):
        """
        Lists names of all local databases.
        """

        query = "SELECT datname FROM pg_database ORDER by datname;"
        result = self.run_queries(query, database=DEFAULT_DATABASE)
        databases = []

        if not result or not isinstance(result, list):
            return databases

        for database in result:
            databases.append(database[0])

        return databases

    def db_exists(self, database=None):
        """
        Checks whether a database with the given name already exists and is an Odoo database.
        """
        database = self._get_database(database)
        return database in self.db_list()

    def db_exists_all(self, database=None):
        """
        Checks whether a database with the given name already exists, even if it is not
        an Odoo database.
        """
        database = self._get_database(database)
        return database in self.db_list_all()

    def is_odoo_db(self, database=None):
        query = """SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON (n.oid = c.relnamespace)
            WHERE c.relname = 'ir_module_module'
            AND c.relkind IN ('r', 'v', 'm')
            AND n.nspname = current_schema"""

        result = self.run_queries(query, database, False)
        return result and isinstance(result, list) and len(result) == 1

    def check_database(self, database=None):
        """
        Checks whether the database both exists and is an Odoo database.
        """
        database = self._get_database(database)
        if not self.db_exists_all(database):
            raise InvalidDatabase(f"Database '{database}' does not exists")
        elif not self.db_exists(database) and not self.is_odoo_db(database):
            raise InvalidOdooDatabase(f"Database '{database}' is not an Odoo database")

    def db_base_version(self, database=None):
        """
        Gets the version number of a database.
        """
        database = self._get_database(database)
        self.check_database(database)

        query = "SELECT latest_version FROM ir_module_module WHERE name = 'base';"
        result = self.run_queries(query, database=database)

        if not result or not isinstance(result, list):
            raise InvalidOdooDatabase(f"Database '{database}' is not an Odoo database")

        result = result[0][0]
        return result

    def db_version_clean(self, database: Optional[str] = None) -> str:
        """
        Gets the Odoo version number of a database.
        """
        version: str = self.db_base_version(database=database)
        return get_odoo_version(version)

    def db_version_parsed(self, database: Optional[str] = None) -> Version:
        """
        Gets the parsed version of a database that can be used for comparisons.
        """
        version: str = self.db_base_version(database=database)
        return parse_odoo_version(version)

    def db_version_full(self, database=None):
        """
        Gets the full version of the database.
        """
        database = self._get_database(database)

        version = self.db_version_clean(database)
        enterprise = self.db_enterprise(database)

        return f"Odoo {version} ({'enterprise' if enterprise else 'standard'})"

    def db_enterprise(self, database=None):
        """
        Checks whether a database is running on the enterprise version of Odoo.
        """
        database = self._get_database(database)

        self.check_database(database)

        query = "SELECT TRUE FROM ir_module_module WHERE name LIKE '%enterprise' LIMIT 1;"

        with PSQL(database) as psql:
            result = psql.query(query)

        if not result:
            return False
        else:
            return True

    def db_is_neutralized(self, database=None):
        """
        Checks whether a database has been cleaned / neuteralized.
        """
        database = self._get_database(database)

        self.check_database(database)

        # TODO: check also config? Or should it not be trusted?

        with PSQL(database) as psql:
            is_neutralized = psql.query(
                """
                SELECT TRUE
                  FROM ir_config_parameter
                 WHERE key = 'database.is_neutralized' AND lower(value) IN ('true', '1');
                """
            )
            if is_neutralized:
                return True

            has_enterprise_code = psql.query(
                "SELECT TRUE FROM ir_config_parameter WHERE key = 'database.enterprise_code';"
            )
            if not has_enterprise_code:
                return True

            has_cleaned_users = psql.query("SELECT TRUE FROM res_users WHERE password IN ('odoo', 'admin');")
            if has_cleaned_users:
                return True

        return False

    def db_pid(self, database=None):
        """
        Gets the PID of a currently running database.
        """
        database = self._get_database(database)

        command = f"""ps aux | grep -E './odoo-bin\\s-d\\s{database}\\s' | awk \'NR==1{{print $2}}\'"""
        stream = os.popen(command)
        pid = stream.read().strip()

        return pid or None

    def db_runs(self, database=None):
        """
        Checks whether the database is currently running.
        """
        database = self._get_database(database)

        return bool(self.db_pid(database))

    def db_command(self, database=None):
        """
        Gets the command which has been used to start the Odoo server for a given database.
        """
        database = self._get_database(database)

        self.check_database(database)

        if not self.db_runs(database):
            raise Exception(f"Database '{database}' is not running")

        command = f"""ps aux | grep -E './odoo-bin\\s-d\\s{database}\\s\'"""
        stream = os.popen(command)
        cmd = stream.read().strip()
        match = RE_COMMAND.search(cmd)

        if not match:
            return None

        cmd = match.group(0)

        return cmd or None

    def db_port(self, database=None):
        """
        Checks on which port the database is currently running.
        """
        database = self._get_database(database)

        port = None

        if self.db_runs(database):
            command = self.db_command(database)
            assert command
            match = RE_PORT.search(command)

            if match:
                port = match.group(2)
            else:
                port = 8069

        return str(port)

    def db_url(self, database=None):
        """
        Returns the local url to the Odoo web application.
        """
        database = self._get_database(database)

        if not self.db_runs(database):
            return None

        return f"http://localhost:{self.db_port(database)}/web"

    def db_filestore(self, database=None):
        """
        Returns the absolute path to the filestore of a given database.
        """
        database = self._get_database(database)
        return f"{Path.home()}/.local/share/Odoo/filestore/{database}"

    def ensure_stopped(self, database=None):
        """
        Throws an error if the database is running.
        """
        database = self._get_database(database)
        self.check_database(database)

        if self.db_runs(database):
            raise Exception(f"Database {database} is running, please shut it down and retry")

    def ensure_running(self, database=None):
        """
        Throws an error if the database is not running.
        """
        database = self._get_database(database)
        self.check_database(database)

        if not self.db_runs(database):
            raise Exception(f"Database {database} is not running, please start it up and retry")

    def db_size(self, database=None):
        """
        Gets the size of the PSQL database in bytes.
        """
        database = self._get_database(database)
        self.check_database(database)

        result = self.run_queries(f"SELECT pg_database_size('{database}') LIMIT 1", database=database)

        if not result or not isinstance(result, list):
            return 0.0

        return result[0][0]

    def db_filestore_size(self, database=None):
        """
        Gets the size of the filestore linked to the database.
        """

        database = self._get_database(database)
        self.check_database(database)
        path = Path(self.db_filestore(database))
        return sum(f.stat().st_size for f in path.glob("**/*") if f.is_file()) or 0.0


class TemplateDBCommand(LocalDatabaseCommand):
    """
    Command class for dealing with Template restoration
    """

    arguments = [
        {
            "aliases": ["-t", "--template"],
            "dest": "from_template",
            "action": "store_true",
            "help": "Delete the database and restore the template before launching Odoo",
        },
    ]


class TemplateCreateDBCommand(LocalDatabaseCommand):
    """
    Command class for dealing with Template creation
    """

    arguments = [
        {
            "aliases": ["-t", "--template"],
            "dest": "create_template",
            "action": "store_true",
            "help": "Create a template right after restore",
        },
    ]


class GitHubCommand(Command, ABC):
    """
    Command class for interacting with GitHub through odev.
    """

    arguments = [
        {
            "aliases": ["-t", "--token"],
            "help": "GitHub authentication token",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.github: Github = get_github(args.token)


class OdooBinMixin(LocalDatabaseCommand, ABC):
    arguments = [
        {
            "name": "addons",
            "action": CommaSplitAction,
            "nargs": "?",
            "help": "Comma-separated list of additional addon paths",
        },
        {
            "name": "args",
            "nargs": REMAINDER,
            "help": """
            Additional arguments to pass to odoo-bin; Check the documentation at
            https://www.odoo.com/documentation/14.0/fr/developer/misc/other/cmdline.html
            for the list of available arguments
            """,
        },
        {
            "aliases": ["--pull"],
            "dest": "pull",
            "action": "store_true",
            "help": "Pull the new versions of Odoo Community, Enterprise, Design-Themes and Upgrades repositories",
        },
        {
            "aliases": ["--venv"],
            "dest": "alt_venv",
            "action": "store_true",
            "help": "Create an alternative venv (database name)",
        },
        {
            "aliases": ["-s", "--save"],
            "dest": "save",
            "action": "store_true",
            "help": "Save the current db cli arguments for the next runs",
        },
    ]

    odoobin_subcommand: ClassVar[Optional[str]] = None
    """
    Optional subcommand to pass to `odoo-bin` at execution time.
    """

    use_config_args: bool = False
    """
    Whether to load (and save if `--save`) cli arguments and addons saved in the database's config.
    """

    always_save_config_args: bool = False
    """
    Whether to always save (ie. overwrite) arguments and addons to the database's config.
    """

    def __init__(self, args: Namespace):
        super().__init__(args)

        self.config_args_key: str = f"args_{self.name}"
        self.config_addons_key: str = "addons"

        self.addons: List[str] = args.addons or []
        self.additional_args: List[str] = args.args

        if self.use_config_args:
            config_args, config_addons = self.load_db_config_cli_args()

            save_confirm_msg = "Arguments have already been saved for this database, do you want to override them?"
            if self.always_save_config_args or (
                args.save and (not (config_args or config_addons) or _logger.confirm(save_confirm_msg))
            ):
                self.save_db_config_cli_args()

    def load_db_config_cli_args(self) -> Tuple[List[str], List[str]]:
        config_args: List[str] = shlex.split(self.config["databases"].get(self.database, self.config_args_key, ""))
        config_addons: List[str] = self.config["databases"].get(self.database, self.config_addons_key, "").split(",")

        self.addons = self.addons or config_addons + (
            [config_args.pop(0)] if config_args and is_addon_path(config_args[0]) else []
        )
        self.additional_args = self.additional_args or config_args

        return config_args, config_addons

    def save_db_config_cli_args(self) -> None:
        with self.config["databases"] as dbs_config:
            db_cfg_section = dbs_config[self.database]
            db_cfg_section[self.config_args_key] = shlex.join(self.additional_args)
            db_cfg_section[self.config_addons_key] = ",".join(self.addons)

    def run_odoo(
        self, check_last_run: bool = False, set_last_run: bool = True, **kwargs
    ) -> subprocess.CompletedProcess:
        repos_path: str = self.config["odev"].get("paths", "odoo")
        version: str = kwargs.pop("version", None) or self.db_version_clean()
        database = kwargs.pop("database", self.database)
        venv_name: Optional[str] = (
            self.database
            if self.args.alt_venv or os.path.isdir(odoo.get_venv_path(repos_path, version, self.database))
            else None
        )
        default_args = {
            "repos_path": repos_path,
            "version": version,
            "database": database,
            "addons": self.addons,
            "subcommand": self.odoobin_subcommand,
            "additional_args": self.additional_args,
            "venv_name": venv_name,
            "skip_prompt": self.args.pull,
        }

        with self.config["databases"] as dbs_config:
            if check_last_run:
                last_run: Optional[str] = dbs_config.get(database, "last_run")
                default_args["last_run"] = datetime.fromisoformat(last_run) if last_run else None

        return odoo.run_odoo(**{**default_args, **kwargs})


# TODO: reuse this mixin for all commands that use odoo.com credentials (dump... uhh... just dump)
class OdooComCliMixin(Command, ABC):
    """
    Base class with common functionality for commands running on odoo.sh
    """

    arguments = [
        {
            "aliases": ["-l", "--login"],
            "help": "Username for GitHub or Odoo SH login",
        },
        {
            "aliases": ["-p", "--password"],
            "help": "Password for GitHub or Odoo SH login",
        },
        {
            "aliases": ["-r", "--reason"],
            "help": "Fill the reason field when login with /_odoo/support",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.login: Optional[str] = args.login
        self.password: Optional[str] = args.password


class OdooUpgradeRepoMixin(Command, ABC):
    """
    Mixin to include in commands using (custom) upgrade repo
    """

    arguments = [
        {
            "aliases": ["--upgrade-repo-path"],
            "help": "Local path of the `upgrade` repository clone",
        },
        {
            "aliases": ["--custom-util-repo-path", "--psbe-upgrade-repo-path"],
            "help": "Local path of the `custom-util` repository clone",
        },
    ]

    upgrade_repo_path: Optional[str] = None
    custom_util_repo_path: Optional[str] = None

    def get_upgrade_repo_paths(self, args: Namespace) -> Dict[str, str]:
        """
        Extracts the upgrade (custom) upgrade repository paths from args or config
        Updates config if args are present
        """
        config = ConfigManager("odev")
        # TODO: can we clone these automatically instead?
        upgrade_repo_parameter_to_path_keys = {"upgrade_repo_path", "custom_util_repo_path"}
        upgrade_repo_parameter_to_path: Dict[str, str] = {}

        for upgrade_repo_parameter in upgrade_repo_parameter_to_path_keys:
            try:
                args_repo_path: str = getattr(args, upgrade_repo_parameter)
                self.validate(args_repo_path)
                path = os.path.realpath(os.path.normpath(args_repo_path))
                upgrade_repo_parameter_to_path[upgrade_repo_parameter] = path
                config.set("paths", upgrade_repo_parameter, path)
            except (AttributeError, ValueError):
                upgrade_repo_parameter_to_path[upgrade_repo_parameter] = config.get("paths", upgrade_repo_parameter)

        return upgrade_repo_parameter_to_path

    @staticmethod
    def validate(path: Optional[str]) -> bool:
        if not path or not os.path.exists(path):
            raise ValueError(f"Path doesn't exist: {path}")
        else:
            return True


class OdooSHDatabaseCommand(OdooComCliMixin, Command, ABC):
    """
    Base class with common functionality for commands running on odoo.sh
    """

    sh_connector: ShConnector
    """
    Connector to Odoo SH
    """

    arguments = [
        {
            "aliases": ["project"],
            "metavar": "SH_PROJECT",
            "help": "the name of the SH project / github repo, eg. psbe-client",
        },
        {
            "aliases": ["-gu", "--github-user"],
            "help": "username of the github user for odoo.sh login",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        if not args.project:
            raise ValueError("Invalid SH project / repo")
        self.sh_repo: str = args.project

        self.github_user: str = args.github_user

        _logger.info("Connecting to odoo.sh")
        self.sh_connector: ShConnector = get_sh_connector(
            self.login, self.password, self.sh_repo, self.github_user
        ).impersonate()


class OdooSHBranchCommand(OdooSHDatabaseCommand, ABC):
    """
    Base class with common functionality for running commands on an Odoo SH branch.
    """

    ssh_url: Optional[str] = ""
    """
    URL to the current build for the selected branch on Odoo SH.
    """

    paths_to_cleanup: List[str] = []
    """
    Paths to target when performing cleanup actions.
    """

    arguments = [
        {
            "name": "branch",
            "metavar": "SH_BRANCH",
            "help": "Name of the Odoo SH or GitHub branch to target",
        },
    ]

    def __init__(self, args: Namespace):
        if not args.branch:
            raise InvalidArgument("Invalid SH / GitHub branch")

        self.sh_branch = args.branch

        super().__init__(args)

        self.ssh_url = self.sh_connector.get_last_build_ssh(self.sh_branch)
        self.paths_to_cleanup: List[str] = []

    def ssh_run(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """
        Run an SSH command in the current branch.
        Has the same signature as :func:`ShConnector.ssh_command` except for the
        ``ssh_url`` argument that's already provided.
        """

        return self.sh_connector.ssh_command(self.ssh_url, *args, **kwargs)

    def test_ssh(self) -> None:
        """
        Tests ssh connectivity for the odoo.sh branch
        """

        if not self.ssh_url:
            raise ValueError(f"SSH url unavailable for {self.sh_repo}/{self.sh_branch}")

        _logger.debug(f"Testing SSH connectivity to SH branch {self.ssh_url}")
        result = self.ssh_run(
            ["uname", "-a"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if result.returncode != 0:
            _logger.error(result.stdout)

            if "Permission denied (publickey)" in result.stdout:
                raise PermissionError("Got permission denied error from SSH. Did you enable ssh-agent?")
            result.check_returncode()  # raises
        _logger.debug(f"SSH connected successfully: {result.stdout}")

    def copy_to_sh_branch(
        self,
        *sources: str,
        dest: str,
        dest_as_dir: bool = False,
        to_cleanup: bool = False,
        show_progress: bool = False,
    ) -> None:
        """
        Copy files with rsync to the SH branch.
        :param sources: one or multiple sources to copy over.
        :param dest: the destination path to copy to.
        :param dest_as_dir: if true, ensures the ``dest`` path has a trailing `/`,
            indicating it's a directory and any sources will have to be copied into it.
            Defaults to `False`.
        :param to_cleanup: registers the copied paths for cleanup afterwards.
        """
        if dest_as_dir and not dest.endswith("/"):
            dest = dest + "/"
        if not dest.endswith("/") and len(sources) > 1:
            dest_as_dir = True
        if to_cleanup:
            # Let's set this before, so we can also clean up partial transfers
            if dest_as_dir:
                self.paths_to_cleanup += [os.path.join(dest, os.path.basename(s)) for s in sources]
            else:
                self.paths_to_cleanup.append(dest.rstrip("/"))

        full_dest: str = f"{self.ssh_url}:{dest}"
        sources_info: str = ", ".join(f"`{s}`" for s in sources)
        _logger.debug(f"Copying {sources_info} to `{full_dest}`")

        with capture_signals():
            subprocess.run(
                [
                    "rsync",
                    "-a",
                    *(["--info=progress2"] if show_progress else []),
                    "--exclude=__pycache__",
                    *sources,
                    full_dest,
                ],
                check=True,
            )

    def wait_for_build(
        self,
        check_success: bool = False,
        print_progress: bool = True,
        build_appear_timeout: Optional[float] = 30.0,
        last_tracking_id: Optional[int] = None,
    ):
        if last_tracking_id is None:
            branch_history_before = self.sh_connector.branch_history(self.sh_branch)
            last_tracking_id = branch_history_before[0]["id"] if branch_history_before else 0
        start_time: float = time.monotonic()
        tracking_id: Optional[int] = None
        last_message = "Waiting for SH build to appear..."
        poll_interval: float = 4.0
        pbar: Optional[SpinnerBar]
        pbar_context: Union[ContextManager, SpinnerBar]
        loop: Iterator
        if print_progress:
            pbar = SpinnerBar(last_message)
            pbar_context = pbar
            loop = pbar.loop(poll_interval)
        else:
            pbar = None
            pbar_context = nullcontext()
            loop = poll_loop(poll_interval)
        with pbar_context:
            for _ in loop:
                tick: float = time.monotonic()

                # wait for build to appear
                # N.B. SH likes to swap build ids around, so the only good way to follow
                # one is to get it from the tracking record (ie. branch history)
                new_branch_history: Optional[List[MutableMapping[str, Any]]]
                branch_history_domain: List[List]
                if not tracking_id:  # still have to discover last tracking
                    branch_history_domain = [["id", ">", last_tracking_id]]
                else:  # following the build tracking
                    branch_history_domain = [["id", "=", tracking_id]]
                new_branch_history = self.sh_connector.branch_history(
                    self.sh_branch,
                    custom_domain=branch_history_domain,
                )
                build_id: Optional[int] = None
                if new_branch_history:
                    if not tracking_id:
                        last_message = "Build queued..."
                    tracking_id = new_branch_history[0]["id"]
                    build_id = new_branch_history[0]["build_id"][0]

                # fail if timed out
                # TODO: More edge cases, like build disappears?
                if not build_id:
                    if build_appear_timeout and (tick - start_time > build_appear_timeout):
                        raise BuildTimeout(f"Build did not appear within {build_appear_timeout}s")
                    continue

                # get build info (no sanity check)
                build_info: Optional[Mapping[str, Any]]
                build_info = self.sh_connector.build_info(self.sh_branch, build_id=build_id) if build_id else None

                if build_info is None:
                    continue

                status_info: Optional[str]
                status_info = build_info.get("status_info")
                last_message = status_info or last_message
                if pbar is not None:
                    pbar.message = last_message
                build_status: str = build_info["status"]
                if build_status == "updating":
                    _logger.debug(f"SH is building {build_id} on {self.sh_branch}")
                    continue
                if build_status == "done":
                    _logger.info(f"Finished building {build_id} on {self.sh_branch}")
                    if check_success:
                        build_result: Optional[str] = build_info["result"] or None
                        if build_result != "success":
                            exc_class: Type[BuildCompleteException] = BuildFail
                            if build_result == "warning":
                                exc_class = BuildWarning
                            raise exc_class(
                                f"Build {build_id} on {self.sh_branch} "
                                f"not successful ({build_result}): {status_info}",
                                build_info=build_info,
                            )
                    return build_info

    def cleanup_copied_files(self) -> None:
        """
        Runs cleanup actions on copied files previously registered for cleanup.
        """
        if self.paths_to_cleanup:
            _logger.debug("Cleaning up copied paths")
            self.ssh_run(["rm", "-rf", *reversed(self.paths_to_cleanup)])


class ExportCommand(Command, ABC, Template):
    """
    Base class with common functionality to generate code.
    """

    arguments = [
        {
            "aliases": ["--path"],
            "default": os.getcwd(),
            "help": "Path of the folder to create the module (magically generated if clone failed)",
        },
        {
            "aliases": ["--name"],
            "default": "scaffolded_module",
            "help": "Module" "s name",
        },
        {
            "aliases": ["--line_length"],
            "dest": "line_length",
            "type": int,
            "default": 120,
            "help": "Line length",
        },
        {
            "aliases": ["--pretty-off"],
            "action": "store_true",
            "dest": "pretty_off",
            "help": "Pretty off",
        },
        {
            "aliases": ["--pretty-py-off"],
            "action": "store_true",
            "dest": "pretty_py_off",
            "help": "Pretty Py off",
        },
        {
            "aliases": ["--pretty-xml-off"],
            "action": "store_true",
            "dest": "pretty_xml_off",
            "help": "Pretty Xml off",
        },
        {
            "aliases": ["--pretty-import-off"],
            "action": "store_true",
            "dest": "pretty_import_off",
            "help": "Pretty Import off",
        },
        {
            "aliases": ["--autoflake-off"],
            "action": "store_true",
            "dest": "autoflake_off",
            "help": "Autoflake Import off",
        },
        {
            "aliases": ["--version"],
            "type": str,
            "dest": "version",
            "help": "Odoo target version",
            "default": "",
        },
        {
            "aliases": ["--platform", "--type"],
            "choices": ["saas", "sh"],
            "dest": "type",
            "help": "Scaffold type [saas (xml),sh (python)] (default=platform defined on the presale analysis)",
        },
        {
            "aliases": ["-c", "--comment"],
            "action": "store_true",
            "dest": "comment",
            "help": "Add comment to the generated code",
        },
        {
            "aliases": ["-e", "--env"],
            "choices": ["prod", "staging"],
            "default": "prod",
            "help": "Default database to use (use staging for test)",
        },
    ]

    connection: odoolib.Connection
    export_type = "export"
    export_config: Config
    module_name = ""

    def __init__(self, args: Namespace):
        self.type = args.type or "sh"
        super().__init__(args)

    def _init_config(self):
        super()._init_config()

        self.manifest = {
            "name": "",
            "summary": "",
            "description": "",
            "category": [0, ""],
            "author": "Odoo PS",
            "website": "https://www.odoo.com",
            "license": "OEEL-1",
            "version": self._get_version(),
            "depends": set(),
            "data": set(),
            "qweb": set(),
            "assets": defaultdict(list),
            "pre_init_hook": False,
            "post_init_hook": False,
            "uninstall": False,
        }

        self.init = {"class": set(), "pre_init_hook": [], "post_init_hook": [], "uninstall": []}

        self.migration_script = {
            "pre_migrate": {"models": [], "fields": [], "remove_view": set(), "lines": []},
            "post_migrate": {"lines": []},
            "end_migrate": {"lines": []},
        }

    def init_connection(self, hostname, database, login, password, protocol="jsonrpcs", port=443):
        self.connection = odoolib.get_connection(
            hostname=hostname, database=database, login=login, password=password, protocol=protocol, port=port
        )

    def safe_mkdir(self, path: str, module: str = "") -> str:
        module_path = os.path.join(path, module)

        if os.path.exists(module_path):
            if module and not is_really_module(path, module) and os.listdir(module_path):
                raise InvalidFileArgument(
                    f"The folder {module_path} already exist and doesn't seem to be an Odoo module path"
                )
            elif not is_addon_path(path) and os.listdir(path):
                raise InvalidFileArgument(f"The folder {module_path} already exist and is not empty")

            if os.path.isdir(Path(module_path, "odev")):
                raise InvalidFileArgument("Can't be launched without --path inside odev folder")

            if _logger.confirm(f"Module folder {module_path} already exist do you want to delete first ?"):
                _logger.warning(f"Existing folder '{module_path}' successfully deleted")
                shutil.rmtree(module_path)
            else:
                return module_path

        _logger.debug(f"Folder {module_path} successfully created")
        mkdir(module_path)
        return module_path

    def _check_version_match(self, arg_version, db_version):
        if arg_version and arg_version != db_version:
            if not _logger.confirm(
                f"The version provided in argument ({arg_version})"
                f" doesn't match the one from the analysis ({db_version})."
                " Do you want to continue anyway ?"
            ):
                raise InvalidArgument("Command aborted because the version didn't match")

    def _check_and_add_migrate(self, data_type, model, field=None):
        if data_type == "model" and model[:2] == "x_":
            self.migration_script["pre_migrate"]["models"].append({"old_model": model, "new_model": odoo_model(model)})
        elif data_type == "field" and field[:2] == "x_":
            self.migration_script["pre_migrate"]["fields"].append(
                {"old_field": field, "new_field": odoo_field(field), "model": odoo_field(model)}
            )

    def _get_version(self, short=False) -> Version:
        version = str(self.export_config.version).split(".")

        if not short:
            version.extend(["1", "0", "0"])

        return Version(".".join(map(str, version)))

    def _generate_init(self):
        cfg = self.export_config.config["init"]

        if self.type == "saas":
            self.init["class"] = []
        elif self.type == "sh":
            self.init["class"] = list(self.init["class"])
            self.init["class"].sort()

            if self.init["class"]:
                self.generate_template({"class": self.init["class"]}, cfg)

            self.init["class"] = ["models"]

        main_init = cfg.copy()
        main_init.update({"folder_name": "."})

        self.generate_template(self.init, main_init)

    def _generate_manifest(self):
        cfg = self.export_config.config["manifest"]

        self.manifest["depends"] = list(self.manifest["depends"])
        self.manifest["depends"].sort()
        self.manifest["data"] = [path.replace("\\", "/") for path in self.manifest["data"]]
        self.manifest["data"].sort()

        self.generate_template(self.manifest, cfg)

    def _generate_icon(self):
        icon_path = os.path.join(self.args.path, self.module_name, "static", "description")

        url_param = {
            "color": random.choice(ICON_COLORS),
            "class_name": "",
        }

        if not os.path.exists(icon_path):
            os.makedirs(icon_path)

        imgkit.from_url(
            "https://ps-tools.odoo.com/icon?" + urllib.parse.urlencode(url_param),
            icon_path + "/icon.png",
            options=ICON_OPTIONS,
        )

    def _copy_files(self, module=""):
        files = [
            ".gitignore",
        ]

        for file in files:
            path_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates/static/", file)

            shutil.copy(path_file, self.args.path)

        cfg = self.export_config.config["readme"]
        self.generate_template({"module_name": self.module_name.replace("_", "").title()}, cfg)

        odoo_version = self._get_version(True)
        if not self.no_pre_commit and odoo_version >= Version("13.0"):
            fetch_pre_commit_config(dst_path=self.args.path, version=odoo_version)

    def _generate_mig_script(self):
        if self.type == "saas":
            return

        copy_script = False
        module_version = self.manifest["version"]
        version = re.match(r"^([\d]+\.[\d]+)\.([\d\.]+)$", str(module_version))

        if version:
            module_version = version[2]

        dest = os.path.join("migrations/", str(self._get_version(True)) + "." + str(module_version))

        for migration_type in ["end", "pre", "post"]:
            cfg = self.export_config.config[migration_type + "-10"]
            cfg.update({"folder_name": dest})

            migration_script = self.migration_script[migration_type + "_migrate"]
            generate = bool(migration_script["lines"])

            if migration_type == "pre":
                for key in ["models", "fields", "remove_view"]:
                    generate = generate or migration_script[key]

            if generate:
                self.generate_template(migration_script, cfg)
                copy_script = generate

        if copy_script:
            util_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates/static/", "util.py")

            shutil.copy(util_file, os.path.join(self.args.path, self.module_name, "migrations"))
