'''Command-line commands base classes and utility functions'''

from odev.exceptions.commands import InvalidQuery
import os
import sys
import inspect
import textwrap
import subprocess
import time
from pathlib import Path
from contextlib import nullcontext
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from github import Github
from typing import (
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
    Type,
    Union,
)

from packaging.version import Version

from odev.utils import logging
from odev.utils.github import get_github
from odev.utils.signal import capture_signals
from odev.utils.spinner import SpinnerBar, poll_loop
from odev.utils.shconnector import get_sh_connector, ShConnector
from odev.utils.config import ConfigManager
from odev.utils.psql import PSQL
from odev.utils.odoo import check_database_name, parse_odoo_version, get_odoo_version
from odev.structures.actions import OptionalStringAction
from odev.constants import RE_COMMAND, RE_PORT, DEFAULT_DATABASE
from odev.exceptions import (
    InvalidDatabase,
    InvalidOdooDatabase,
    InvalidArgument,
    BuildCompleteException,
    BuildFail,
    BuildTimeout,
    BuildWarning,
)


logger = logging.getLogger(__name__)


class BaseCommand(ABC):
    '''
    Base class for handling commands.
    '''

    name: ClassVar[str]
    '''
    The name of the command associated with the class. Must be unique.
    '''

    config: Dict[str, ConfigManager] = {}
    '''
    General configuration for odev and databases.
    '''

    aliases: ClassVar[Sequence[str]] = []
    '''
    Additional aliases for the command. These too must be unique.
    '''

    subcommands: ClassVar[MutableMapping[str, 'CommandType']] = {}
    '''
    Subcommands' classes available for this command.
    '''

    command: ClassVar[Optional['CommandType']] = None
    '''
    Parent command class.
    '''

    parent: ClassVar[Optional[str]] = None
    '''
    Name of the parent command, for auto linking.
    '''

    help: ClassVar[Optional[str]] = None
    '''
    Optional help information on what the command does.
    '''

    help_short: ClassVar[Optional[str]] = None
    '''
    Optional short help information on what the command does.
    If omitted, the class or source module docstring will be used instead.
    '''

    arguments: ClassVar[List[MutableMapping[str, Any]]] = [
        dict(
            aliases=['-y', '--yes'],
            dest='assume_yes',
            action='store_true',
            help='Assume `yes` as answer to all prompts and run non-interactively',
        ),
        dict(
            aliases=['-n', '--no'],
            dest='assume_no',
            action='store_true',
            help='Assume `no` as answer to all prompts and run non-interactively',
        ),
        dict(
            aliases=['-v', '--log-level'],
            choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'],
            default='INFO',
            help='Set logging verbosity',
        ),
    ]
    '''
    Optional arguments definition to extend commands capabilities.
    '''

    is_abstract: ClassVar[bool] = False

    def __init__(self, args: Namespace):
        '''
        Initialize the command runner.

        :param args: the parsed arguments as an instance of :class:`Namespace`
        '''

        if args.assume_yes and args.assume_no:
            raise InvalidArgument('Arguments `assume_yes` and `assume_no` cannot be used together')

        logging.interactive = not (args.assume_yes or args.assume_no)
        logging.assume_yes = args.assume_yes or not args.assume_no
        logging.set_log_level(args.log_level)
        self.args: Namespace = args
        self.argv: Optional[Sequence[str]] = None

        if not logging.interactive:
            logger.info(f'''Assuming '{'yes' if logging.assume_yes else 'no'}' for all confirmation prompts''')

        for key in ['odev']:
            self.config[key] = ConfigManager(key)

    @classmethod
    def prepare(cls):
        '''
        Set proper name and help descriptions attributes.
        Also implement inheriting arguments from parent classes.
        '''
        cls.name = (cls.name or cls.__name__).lower()
        cls.is_abstract = inspect.isabstract(cls) or ABC in cls.__bases__
        cls.help = textwrap.dedent(
            cls.__dict__.get('help')
            or cls.__doc__
            or cls.help
            or sys.modules[cls.__module__].__doc__
            or ''
        ).strip()
        cls.help_short = textwrap.dedent(cls.help_short or cls.help).strip()

        cls.arguments = cls._get_merged_arguments()

    @classmethod
    def _get_merged_arguments(cls) -> List[MutableMapping[str, Any]]:
        merged_arguments: MutableMapping[str, MutableMapping[str, Any]] = {}
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
                merged_argument: MutableMapping[str, Any]
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
        '''
        Prepares the argument parser for the :class:`CliCommand` class.

        :return: a instance of :class:`ArgumentParser` prepared with all the arguments
            defined in the command an in its parent's classes.
        '''
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
        '''
        Prepares the argument parser for the :class:`Command` subclass.
        '''
        for argument in cls.arguments:
            params = dict(argument)
            params.pop('name')
            aliases = params.pop('aliases')

            parser.add_argument(*aliases, **params)

    @classmethod
    def run_with(cls, *args, **kwargs) -> Any:
        '''
        Runs the command directly with the provided arguments, bypassing parsers
        '''
        # TODO: automatically fill missing args with None?
        return cls(Namespace(**dict(*args, **kwargs))).run()

    @abstractmethod
    def run(self) -> int:
        '''
        The actual script to run when calling the command.
        '''
        raise NotImplementedError()

    def get_arg(self, name, default=None):
        return getattr(self.args, name, default)


class Command(BaseCommand):
    '''
    Basic command to run from the terminal.
    '''


class LocalDatabaseCommand(Command, ABC):
    '''
    Command class for interacting with local databases through the terminal.
    '''

    options = []

    database_required = True
    '''
    Whether a database is required when running this command or not.
    '''

    add_database_argument = True
    '''
    If set to `False`, no default `database` argument will be added.
    '''

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        if cls.add_database_argument and not any(a.get('name') == 'database' for a in cls.arguments):
            parser.add_argument(
                'database',
                action=OptionalStringAction,
                nargs=1 if cls.database_required else '?',
                help='Name of the local database to target',
            )
        super().prepare_arguments(parser)

    def __init__(self, args: Namespace):
        super().__init__(args)

        for key in ['databases']:
            self.config[key] = ConfigManager(key)

        self.database = self.database_required and self._get_database(database=args.database) or ''

    def _get_database(self, database=None) -> str:
        database = database or self.database
        check_database_name(database or self.database)
        return database

    def run_queries(self, queries=None, database=None, raise_on_error=True):
        '''
        Runs queries on the Postgresql instance of a database.
        '''
        database = self._get_database(database)
        result = None

        if queries:
            if not isinstance(queries, list):
                queries = [queries]

            with PSQL(database) as psql:
                try:
                    result = psql.query('; '.join(queries))
                except Exception as e:
                    if raise_on_error:
                        raise InvalidQuery(e)
                    return None

            if any(query.lower().startswith('select') for query in queries):
                return result
            else:
                return True

    def db_list(self):
        '''
        Lists names of local Odoo databases.
        '''
        return self.config['databases'].sections()

    def db_list_all(self):
        '''
        Lists names of all local databases.
        '''

        query = 'SELECT datname FROM pg_database ORDER by datname;'
        result = self.run_queries(query, database=DEFAULT_DATABASE)
        databases = []

        if not result or not isinstance(result, list):
            return databases

        for database in result:
            databases.append(database[0])

        return databases

    def db_exists(self, database=None):
        '''
        Checks whether a database with the given name already exists and is an Odoo database.
        '''
        database = self._get_database(database)
        return database in self.db_list()

    def db_exists_all(self, database=None):
        '''
        Checks whether a database with the given name already exists, even if it is not
        an Odoo database.
        '''
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
        '''
        Checks whether the database both exists and is an Odoo database.
        '''
        database = self._get_database(database)
        if not self.db_exists_all(database):
            raise InvalidDatabase('Database \'%s\' does not exists' % (database))
        elif not self.db_exists(database) and not self.is_odoo_db(database):
            raise InvalidOdooDatabase('Database \'%s\' is not an Odoo database' % (database))

    def db_base_version(self, database=None):
        '''
        Gets the version number of a database.
        '''
        database = self._get_database(database)
        self.check_database(database)

        query = 'SELECT latest_version FROM ir_module_module WHERE name = \'base\';'
        result = self.run_queries(query, database=database)

        if not result or not isinstance(result, list):
            raise InvalidOdooDatabase('Database \'%s\' is not an Odoo database' % (database))

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
        '''
        Gets the full version of the database.
        '''
        database = self._get_database(database)

        version = self.db_version_clean(database)
        enterprise = self.db_enterprise(database)

        return 'Odoo %s (%s)' % (version, 'enterprise' if enterprise else 'standard')

    def db_enterprise(self, database=None):
        '''
        Checks whether a database is running on the enterprise version of Odoo.
        '''
        database = self._get_database(database)

        self.check_database(database)

        query = 'SELECT TRUE FROM ir_module_module WHERE name LIKE \'%enterprise\' LIMIT 1;'

        with PSQL(database) as psql:
            result = psql.query(query)

        if not result:
            return False
        else:
            return True

    def db_pid(self, database=None):
        '''
        Gets the PID of a currently running database.
        '''
        database = self._get_database(database)

        command = f'''ps aux | grep -E './odoo-bin\\s-d\\s{database}\\s' | awk \'NR==1{{print $2}}\''''
        stream = os.popen(command)
        pid = stream.read().strip()

        return pid or None

    def db_runs(self, database=None):
        '''
        Checks whether the database is currently running.
        '''
        database = self._get_database(database)

        return bool(self.db_pid(database))

    def db_command(self, database=None):
        '''
        Gets the command which has been used to start the Odoo server for a given database.
        '''
        database = self._get_database(database)

        self.check_database(database)

        if not self.db_runs(database):
            raise Exception('Database \'%s\' is not running' % (database))

        command = f'''ps aux | grep -E './odoo-bin\\s-d\\s{database}\\s\''''
        stream = os.popen(command)
        cmd = stream.read().strip()
        match = RE_COMMAND.search(cmd)

        if not match:
            return None

        cmd = match.group(0)

        return cmd or None

    def db_port(self, database=None):
        '''
        Checks on which port the database is currently running.
        '''
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
        '''
        Returns the local url to the Odoo web application.
        '''
        database = self._get_database(database)

        if not self.db_runs(database):
            return None

        return 'http://localhost:%s/web' % (self.db_port(database))

    def db_filestore(self, database=None):
        '''
        Returns the absolute path to the filestore of a given database.
        '''
        database = self._get_database(database)
        return '%s/.local/share/Odoo/filestore/%s' % (Path.home(), database)

    def ensure_stopped(self, database=None):
        '''
        Throws an error if the database is running.
        '''
        database = self._get_database(database)
        self.check_database(database)

        if self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

    def ensure_running(self, database=None):
        '''
        Throws an error if the database is not running.
        '''
        database = self._get_database(database)
        self.check_database(database)

        if not self.db_runs(database):
            raise Exception('Database %s is not running, please start it up and retry' % (database))

    def db_size(self, database=None):
        '''
        Gets the size of the PSQL database in bytes.
        '''
        database = self._get_database(database)
        self.check_database(database)

        result = self.run_queries(
            'SELECT pg_database_size(\'%s\') LIMIT 1' % database,
            database=database
        )

        if not result or not isinstance(result, list):
            return 0.0

        return result[0][0]

    def db_filestore_size(self, database=None):
        '''
        Gets the size of the filestore linked to the database.
        '''

        database = self._get_database(database)
        self.check_database(database)
        path = Path(self.db_filestore(database))
        return sum(f.stat().st_size for f in path.glob('**/*') if f.is_file()) or 0.0


class GitHubCommand(Command, ABC):
    '''
    Command class for interacting with GitHub through odev.
    '''

    arguments = [
        dict(
            aliases=['-t', '--token'],
            help='GitHub authentication token',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.github: Github = get_github(args.token)


# TODO: reuse this mixin for all commands that use odoo.com creds (dump... uhh... just dump)
class OdooComCliMixin(Command, ABC):
    """
    Base class with common functionality for commands running on odoo.sh
    """

    arguments = [
        dict(
            aliases=['-l', '--login'],
            help='Username for GitHub or Odoo SH login',
        ),
        dict(
            aliases=['-p', '--password'],
            help='Password for GitHub or Odoo SH login',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.login: Optional[str] = args.login
        self.password: Optional[str] = args.password


class OdooSHDatabaseCommand(OdooComCliMixin, Command, ABC):
    """
    Base class with common functionality for commands running on odoo.sh
    """

    sh_connector: ShConnector
    '''
    Connector to Odoo SH
    '''

    arguments = [
        dict(
            aliases=['repo'],
            metavar="REPO",
            help='the name of the SH project / github repo, eg. psbe-client',
        ),
        dict(
            aliases=['-gu', '--github-user'],
            help='username of the github user for odoo.sh login',
        ),
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)

        if not args.repo:
            raise ValueError("Invalid SH project / repo")
        self.sh_repo: str = args.repo

        self.github_user: str = args.github_user

        logger.info("Connecting to odoo.sh")
        self.sh_connector: ShConnector = get_sh_connector(
            self.login, self.password, self.sh_repo, self.github_user
        )


class OdooSHBranchCommand(OdooSHDatabaseCommand, ABC):
    '''
    Base class with common functionality for running commands on an Odoo SH branch.
    '''

    ssh_url: Optional[str] = ''
    '''
    URL to the current build for the selected branch on Odoo SH.
    '''

    paths_to_cleanup: List[str] = []
    '''
    Paths to target when performing cleanup actions.
    '''

    arguments = [
        dict(
            name='branch',
            metavar='BRANCH',
            help='Name of the Odoo SH or GitHub branch to target',
        ),
    ]

    def __init__(self, args: Namespace):
        if not args.branch:
            raise InvalidArgument('Invalid SH / GitHub branch')

        self.sh_branch = args.branch

        super().__init__(args)

        self.ssh_url: str = self.sh_connector.get_last_build_ssh(self.sh_branch)
        self.paths_to_cleanup: List[str] = []

    def ssh_run(self, *args, **kwargs) -> subprocess.CompletedProcess:
        '''
        Run an SSH command in the current branch.
        Has the same signature as :func:`ShConnector.ssh_command` except for the
        ``ssh_url`` argument that's already provided.
        '''

        return self.sh_connector.ssh_command(self.ssh_url, *args, **kwargs)

    def test_ssh(self) -> None:
        '''
        Tests ssh connectivity for the odoo.sh branch
        '''

        if not self.ssh_url:
            raise ValueError(f'SSH url unavailable for {self.sh_repo}/{self.sh_branch}')

        logger.debug(f'Testing SSH connectivity to SH branch {self.ssh_url}')
        result = self.ssh_run(
            ['uname', '-a'],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if result.returncode != 0:
            logger.error(result.stdout)

            if 'Permission denied (publickey)' in result.stdout:
                raise PermissionError(
                    'Got permission denied error from SSH. Did you enable ssh-agent?'
                )
            result.check_returncode()  # raises
        logger.debug(f'SSH connected successfully: {result.stdout}')

    def copy_to_sh_branch(
        self,
        *sources: str,
        dest: str,
        dest_as_dir: bool = False,
        to_cleanup: bool = False,
        show_progress: bool = False,
    ) -> None:
        '''
        Copy files with rsync to the SH branch.
        :param sources: one or multiple sources to copy over.
        :param dest: the destination path to copy to.
        :param dest_as_dir: if true, ensures the ``dest`` path has a trailing `/`,
            indicating it's a directory and any sources will have to be copied into it.
            Defaults to `False`.
        :param to_cleanup: registers the copied paths for cleanup afterwards.
        '''
        if dest_as_dir and not dest.endswith('/'):
            dest = dest + '/'
        if not dest.endswith('/') and len(sources) > 1:
            dest_as_dir = True
        if to_cleanup:
            # Let's set this before, so we can also clean up partial transfers
            if dest_as_dir:
                self.paths_to_cleanup += [
                    os.path.join(dest, os.path.basename(s)) for s in sources
                ]
            else:
                self.paths_to_cleanup.append(dest.rstrip('/'))

        full_dest: str = f'{self.ssh_url}:{dest}'
        sources_info: str = ', '.join(f'`{s}`' for s in sources)
        logger.debug(f'Copying {sources_info} to `{full_dest}`')

        with capture_signals():
            subprocess.run(
                [
                    'rsync',
                    '-a',
                    *(['--info=progress2'] if show_progress else []),
                    '--exclude=__pycache__',
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
            last_tracking_id = (
                branch_history_before[0]["id"] if branch_history_before else 0
            )
        start_time: float = time.monotonic()
        tracking_id: Optional[int] = None
        last_message: str = "Waiting for SH build to appear..."
        poll_interval: float = 2.0
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
                new_branch_history: Optional[List[Mapping[str, Any]]]
                branch_history_domain: List[List]
                if not tracking_id:  # still have to discover last tracking
                    branch_history_domain = [["id", ">", last_tracking_id]]
                else:  # following the build tracking
                    branch_history_domain = [["id", "=", tracking_id]]
                new_branch_history = self.sh_connector.branch_history(
                    self.sh_branch, custom_domain=branch_history_domain
                )
                build_id: Optional[int] = None
                if new_branch_history:
                    if not tracking_id:
                        last_message: str = "Build queued..."
                    tracking_id = new_branch_history[0]["id"]
                    build_id = new_branch_history[0]["build_id"][0]

                # fail if timed out
                # TODO: More edge cases, like build disappears?
                if not build_id:
                    if build_appear_timeout and (
                        tick - start_time > build_appear_timeout
                    ):
                        raise BuildTimeout(
                            f"Build did not appear within {build_appear_timeout}s"
                        )
                    continue

                # get build info (no sanity check)
                build_info: Optional[Mapping[str, Any]]
                build_info = build_id and self.sh_connector.build_info(
                    self.sh_branch, build_id=build_id
                )
                status_info: Optional[str]
                status_info = build_info.get("status_info")
                last_message = status_info or last_message
                if pbar is not None:
                    pbar.message = last_message
                build_status: str = build_info["status"]
                if build_status == "updating":
                    logger.debug(f"SH is building {build_id} on {self.sh_branch}")
                    continue
                if build_status == "done":
                    logger.info(f"Finished building {build_id} on {self.sh_branch}")
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
        '''
        Runs cleanup actions on copied files previously registered for cleanup.
        '''
        if self.paths_to_cleanup:
            logger.debug('Cleaning up copied paths')
            self.ssh_run(['rm', '-rf', *reversed(self.paths_to_cleanup)])


CommandType = Union[
    Type[BaseCommand],
    Type[Command],
    Type[LocalDatabaseCommand],
    Type[GitHubCommand],
    Type[OdooSHDatabaseCommand],
    Type[OdooSHBranchCommand],
]
