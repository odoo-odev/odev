"""PostgreSQL database class."""

import bz2
import gzip
import re
import shutil
import tempfile
from datetime import datetime
from functools import cached_property
from pathlib import Path
from subprocess import PIPE, Popen
from types import FrameType
from typing import (
    IO,
    ClassVar,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
)
from zipfile import ZipFile

from odev.common import bash, progress, string
from odev.common.connectors import PostgresConnector
from odev.common.console import Colors
from odev.common.databases import Branch, Database, Filestore, Repository
from odev.common.logging import logging
from odev.common.mixins import PostgresConnectorMixin, ensure_connected
from odev.common.odoobin import OdoobinProcess
from odev.common.signal_handling import capture_signals
from odev.common.thread import Thread
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


ARCHIVE_DUMP = "dump.sql"
ARCHIVE_FILESTORE = "filestore/"


class LocalDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    _process: Optional[OdoobinProcess] = None
    """The Odoo process running the database."""

    connector: Optional[PostgresConnector] = None
    """The PostgreSQL connector of the database."""

    _whitelisted: bool = False
    """Whether the database is whitelisted and should not be removed automatically."""

    _filestore: Optional[Filestore] = None
    """The filestore of the database."""

    _repository: Optional[Repository] = None
    """The repository containing custom code for the database."""

    _branch: Optional[Branch] = None
    """The branch of the repository containing custom code for the database."""

    _platform: ClassVar[Literal["local"]] = "local"
    """The platform on which the database is running."""

    _platform_display: ClassVar[str] = "Local"
    """The display name of the platform on which the database is running."""

    def __init__(self, name: str):
        """Initialize the database.
        :param name: The name of the database.
        """
        super().__init__(name)

        if self.is_odoo:
            info = self.store.databases.get(self)
            self.whitelisted = info is not None and info.whitelisted

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()
        return self

    def __exit__(self, *args):
        self.psql(self.name).__exit__(*args)

    @property
    def rpc_port(self):
        return self.process and self.process.rpc_port

    @property
    def is_odoo(self) -> bool:
        if not self.exists:
            return False

        with self:
            return self.table_exists("ir_module_module")

    @property
    def venv(self) -> Optional[Path]:
        if not self.is_odoo:
            return None

        info = self.store.databases.get(self)

        if info is None:
            return None

        return Path(info.virtualenv)

    @cached_property
    def version(self) -> Optional[OdooVersion]:
        if not self.is_odoo:
            return None

        with self:
            result = self.is_odoo and self.connector.query(
                """
                SELECT latest_version
                FROM ir_module_module
                WHERE name = 'base'
                LIMIT 1
                """
            )

        return result and result is not True and result[0][0] and OdooVersion(result[0][0]) or None

    @cached_property
    def edition(self) -> Optional[str]:
        if not self.is_odoo:
            return None

        with self:
            result = self.connector.query(
                """
                SELECT true
                FROM ir_module_module
                WHERE license LIKE 'OEEL-%'
                    AND state = 'installed'
                LIMIT 1
                """
            )

        return result and result is not True and result[0][0] and "enterprise" or "community"

    @property
    def filestore(self) -> Filestore:
        if self._filestore is None:
            path: Path = Path.home() / ".local/share/Odoo/filestore/" / self.name
            size: int = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            self._filestore = Filestore(path=path, size=size)

        return self._filestore

    @property
    def url(self) -> Optional[str]:
        if not self.is_odoo:
            return None

        return self.process.is_running and f"http://localhost:{self.process.rpc_port}" or None

    @property
    def size(self) -> int:
        if not self.exists:
            return 0

        with self.psql() as psql:
            result = psql.query(
                f"""
                SELECT pg_database_size('{self.name}')
                LIMIT 1
                """
            )
        return result and result[0][0] or 0

    @property
    def expiration_date(self) -> Optional[datetime]:
        if not self.is_odoo:
            return None

        with self:
            result = self.connector.query(
                """
                SELECT value
                FROM ir_config_parameter
                WHERE key = 'database.expiration_date'
                LIMIT 1
                """
            )

        if not result or result is True:
            return None

        try:
            return datetime.strptime(result[0][0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.strptime(result[0][0], "%Y-%m-%d")

    @property
    def uuid(self) -> Optional[str]:
        if not self.is_odoo:
            return None

        with self:
            result = self.connector.query(
                """
                SELECT value
                FROM ir_config_parameter
                WHERE key = 'database.uuid'
                LIMIT 1
                """
            )

        return result and result is not True and result[0][0] or None

    @property
    def last_date(self) -> Optional[datetime]:
        """The last date the database was used or accessed."""
        last_access = self.last_access_date
        last_usage = self.last_usage_date

        if last_access and last_usage:
            return max(last_access, last_usage)

        return last_access or last_usage

    @property
    def last_usage_date(self) -> Optional[datetime]:
        """The last date the database was used in a command (with odev)."""
        if not self.is_odoo:
            return None

        with self.psql(self.odev.name) as psql:
            result = psql.query(
                f"""
                SELECT date
                FROM history
                WHERE database = '{self.name}'
                ORDER BY date DESC
                LIMIT 1
                """
            )
            return result and result[0][0] or None

    @property
    def last_access_date(self) -> Optional[datetime]:
        if not self.is_odoo:
            return None

        with self:
            result = self.is_odoo and self.connector.query(
                """
                SELECT create_date
                FROM res_users_log
                ORDER BY create_date DESC
                LIMIT 1
                """
            )

        return result and result is not True and result[0][0] or None

    @property
    def exists(self) -> bool:
        """Check if the database exists."""
        with self.psql() as psql, psql.nocache():
            return bool(psql.database_exists(self.name))

    @property
    def running(self) -> bool:
        """Check if the database is running."""
        return self.process is not None and self.process.is_running

    @property
    def process(self) -> Optional[OdoobinProcess]:
        if self._process is None and self.exists:
            with self:
                self._process = OdoobinProcess(self)

        return self._process

    @property
    def repository(self) -> Optional[Repository]:
        if self._repository is None:
            if not self.is_odoo:
                return None

            info = self.store.databases.get(self)

            if not info or not info.repository:
                return None

            organization, name = info.repository.split("/", 1)
            self._repository = Repository(organization=organization, name=name)

        return self._repository

    @repository.setter
    def repository(self, value: Repository):
        """Set the repository of the database."""
        self._repository = value
        self.store.databases.set(self)

    @property
    def branch(self) -> Optional[Branch]:
        if self._branch is None:
            if not self.is_odoo:
                return None

            info = self.store.databases.get(self)

            if not info or not info.branch:
                return None

            self._branch = Branch(name=info.branch, repository=self.repository)

        return self._branch

    @branch.setter
    def branch(self, value: Branch):
        """Set the branch of the database."""
        self._branch = value
        self.store.databases.set(self)

    @property
    def whitelisted(self) -> bool:
        """Whether the database is whitelisted and should not be removed automatically."""
        info = self.store.databases.get(self)
        return not self.is_odoo if info is None else info.whitelisted

    @whitelisted.setter
    def whitelisted(self, value: bool):
        """Set the whitelisted status of the database."""
        self._whitelisted = value
        self.store.databases.set(self)

    @property
    def neutralized(self):
        """Whether the database is neutralized."""
        return self.is_odoo and bool(
            self.query(
                """
                SELECT value
                FROM ir_config_parameter
                WHERE key = 'database.is_neutralized'
                """
            )
        )

    @property
    def installed_modules(self) -> List[str]:
        """List modules that are currently installed on the database."""
        modules: List[Tuple[str]] = self.query(
            """
            SELECT name
            FROM ir_module_module
            WHERE state IN ('installed', 'to upgrade', 'to remove');
            """
        )

        return [module[0] for module in modules]

    def create(self, template: str = None) -> bool:
        """Create the database.

        :param template: The name of the template to copy.
        """
        with self.psql() as psql:
            return psql.create_database(self.name, template=template)

    def drop(self) -> bool:
        if self.connector is not None:
            self.connector.disconnect()
        with self.psql() as psql:
            return psql.drop_database(self.name)

    def neutralize(self):
        installed_modules: List[str] = self.installed_modules
        scripts: List[Path] = [self.odev.static_path / "neutralize-pre.sql"]

        with progress.spinner(f"Looking up neutralization scripts in {len(installed_modules)} installed modules"):
            for addon in self.process.addons_paths:
                for module in installed_modules:
                    neutralize_path: Path = addon / module / "data" / "neutralize.sql"

                    if neutralize_path.is_file():
                        scripts.append(neutralize_path)

        scripts.append(self.odev.static_path / "neutralize-post.sql")

        if self.version.major < 15:
            scripts.append(self.odev.static_path / "neutralize-post-before-15.0.sql")

        tracker = progress.Progress()

        task = tracker.add_task(f"Running {len(scripts)} neutralization scripts", total=len(scripts))
        tracker.start()

        for python_file in scripts:
            tracker.update(task, advance=1, description=self.console.render_str(f"Running {python_file.as_posix()}"))
            self.query(python_file.read_text())

        tracker.stop()

    def dump(self, filestore: bool = False, path: Path = None) -> Optional[Path]:
        if path is None:
            path = self.odev.dumps_path

        path.mkdir(parents=True, exist_ok=True)
        filename = self._get_dump_filename(filestore, suffix="neutralized" if self.neutralized else None)
        file = path / filename

        if file.exists() and not self.console.confirm(f"File {file} already exists. Overwrite it?"):
            return None

        file.unlink(missing_ok=True)

        # By default, TemporaryDirectory creates files under /tmp which on Fedora runs on tmpfs.
        # This filesystem is based on RAM and SWAP and is therefore limited in size to a portion
        # of the total RAM. This is not enough for large database dumps.
        # Moving the temporary directory to /var/tmp solves the issue of size by running on the var
        # partition. Files are still deleted after all operations complete.
        with tempfile.TemporaryDirectory(dir="/var/tmp") as temp_directory:
            temp_file = Path(temp_directory) / filename

            with progress.spinner(f"Dumping PostgreSQL database {self.name!r}"):
                bash.execute(f"pg_dump -d {self.name} > {temp_file}")

            if not filestore:
                shutil.move(temp_file, file)
            else:
                with progress.spinner(f"Writing dump to archive {file}"):
                    shutil.make_archive((file.parent / file.stem).as_posix(), "zip", self.filestore.path)

                    with ZipFile(file, "w") as zip_file:
                        zip_file.write(temp_file.as_posix(), "dump.sql")

        return file

    def restore(self, file: Path):
        if not file.is_file():
            return self.console.error(f"Invalid dump file {file}")

        tracker = progress.Progress(download=True)

        def signal_handler_progress(signal_number: int, frame: Optional[FrameType] = None, message: str = None):
            for task in tracker.tasks:
                if not task.finished:
                    tracker.stop_task(task.id)
                    logger.warning(f"{task.description}: task interrupted by user")

            tracker.stop()
            raise KeyboardInterrupt

        with capture_signals(handler=signal_handler_progress):
            if file.suffix == ".sql":
                self._restore_sql(file, tracker)
            elif file.suffix == ".dump":
                self._restore_dump(file, tracker)
            elif file.suffix == ".zip":
                self._restore_zip(file, tracker)
            elif file.suffix == ".gz":
                self._restore_gzip(file, tracker)
            elif file.suffix in [".bz", ".bz2"]:
                self._restore_bzip(file, tracker)
            else:
                self.console.error(f"Unrecognized extension {file.suffix!r} for dump {file}")

        self = LocalDatabase(self.name)
        tracker.stop()

    def _restore_zip_filestore(self, tracker: progress.Progress, archive: ZipFile):
        """Restore the filestore from a zip archive.
        :param archive: The archive to restore the filestore from.
        :param tracker: An instance of Progress to track the restore process.
        """
        re_filestore_file = re.compile(rf"^{ARCHIVE_FILESTORE}(?P<dirname>[\da-f]{{2}})/(?P<filename>[\da-f]{{40}})$")
        info: List[Tuple[re.Match[str], int]] = [
            (re_filestore_file.match(info.filename), info.file_size)
            for info in archive.filelist
            if re_filestore_file.match(info.filename)
        ]

        if not info:
            return logger.debug("No filestore found in archive")

        logger.debug("Filestore found in archive, restoring")

        if self.filestore.path.exists():
            logger.warning(f"A filestore already exists for database {self.name!r}")
            overwrite_mode: Literal["overwrite", "merge", "keep"] = self.console.select(
                "Overwrite the existing filestore?",
                default="overwrite",
                choices=[
                    ("overwrite", "Remove existing and overwrite with dump"),
                    ("merge", "Merge dump into existing filestore"),
                    ("keep", "Keep existing filestore"),
                ],
            )

            if overwrite_mode == "keep":
                return logger.debug("Keeping existing filestore")

            tracker.start()

            if overwrite_mode == "overwrite":
                shutil.rmtree(self.filestore.path)

        thread = Thread(target=self._restore_zip_filestore_threaded, args=(tracker, archive, info))
        thread.start()

    def _restore_zip_filestore_threaded(
        self,
        tracker: progress.Progress,
        archive: ZipFile,
        info: List[Tuple[re.Match[str], int]],
    ):
        """Thread to monitor the restore process of a zipped dump file and update the progress tracker.
        :param tracker: An instance of Progress to track the restore process.
        :param archive: The archive to restore the filestore from.
        :param info: A list of tuples containing the filestore file path and size.
        """
        filestore_size: int = sum(size for _, size in info)
        task_description: str = (
            f"filestore from {string.stylize(f'{ARCHIVE_FILESTORE!r}', Colors.CYAN)} "
            f"({string.bytes_size(filestore_size)})"
        )
        task_id = tracker.add_task(f"Extracting {task_description}", total=filestore_size)
        tracker.start_task(task_id)
        tracker.start()

        for match, size in info:
            dirname: str = match.group("dirname")
            filename: str = match.group("filename")
            filestore_file_path: Path = self.filestore.path / dirname / filename

            if not filestore_file_path.exists():
                archive.extract(match.string, self.filestore.path)

            tracker.update(task_id, advance=size)

        tracker.remove_task(task_id)
        logger.info(f"Extracted {string.stylize(string.bytes_size(filestore_size), Colors.CYAN)} of filestore data")

    def _restore_buffered_sql(
        self,
        tracker: progress.Progress,
        dump: Union[gzip.GzipFile, bz2.BZ2File, IO[bytes]],
        bytes_count: int,
        mode: Literal["sql", "dump"] = "sql",
    ):
        """Restore SQL data from a buffered dump file.
        :param tracker: An instance of Progress to track the restore process.
        :param dump: The dump file to restore SQL data from.
        :param bytes_count: The total number of bytes to track.
        :param mode: The mode to use when restoring the dump, either `sql` or `dump`.
        """
        # Adding 1 to the bytes count so that the progress bar doesn't reach 100%
        # until the process is complete and the last buffered line has been processed
        extract_task_id = tracker.add_task("Restoring dump from archive", total=bytes_count + 1)
        tracker.start()

        if mode == "dump":
            command = f"pg_restore --dbname {self.name} --single-transaction --disable-triggers --no-owner"
        else:
            command = f"psql --dbname {self.name} --single-transaction"

        psql_process: Popen[bytes] = Popen(command, shell=True, stdin=PIPE, stdout=PIPE, bufsize=-1)
        thread = Thread(target=self._restore_zip_sql_threaded, args=(psql_process,))
        thread.start()

        for line in dump:
            psql_process.stdin.write(line)
            tracker.update(extract_task_id, advance=len(line))

        tracker.update(extract_task_id, advance=1)
        psql_process.stdin.close()

        thread.join()
        tracker.stop()

    def _restore_zip_sql_threaded(self, process: Popen[bytes]):
        """Thread to monitor the restore process of a zipped dump file and update the progress tracker.
        :param process: The process to monitor.
        """
        for _ in iter(process.stdout.readline, b""):
            if process.poll() is not None:
                break

    def _restore_zip(self, file: Path, tracker: progress.Progress):
        """Restore a database from a zip archive containing a dump file and optionally a filestore.
        :param file: The path to the zip archive.
        :param tracker: An instance of Progress to track the restore process.
        """
        with ZipFile(file, "r") as archive:
            if ARCHIVE_DUMP not in archive.namelist():
                return self.console.error(
                    f"Invalid dump file {file.as_posix()}, missing {string.stylize(f'{ARCHIVE_DUMP!r}', Colors.CYAN)} file"
                )

            if ARCHIVE_FILESTORE in archive.namelist():
                self._restore_zip_filestore(tracker, archive)

            with archive.open(ARCHIVE_DUMP) as dump:
                self._restore_buffered_sql(tracker, dump, archive.getinfo(dump.name).file_size)

    def _restore_buffer(self, tracker: progress.Progress, dump: Union[gzip.GzipFile, bz2.BZ2File, IO[bytes]]):
        """Restore a database from a stream containing a dump file and optionally a filestore.
        :param tracker: An instance of Progress to track the restore process.
        :param dump: The buffered dump file to restore SQL data from.
        """
        dump.seek(0, 2)
        bytes_count: int = dump.tell()
        dump.seek(0)
        self._restore_buffered_sql(tracker, dump, bytes_count)

    def _restore_gzip(self, file: Path, tracker: progress.Progress):
        """Restore a database from a gzip archive containing a dump file and optionally a filestore.
        :param file: The path to the gzip archive.
        :param tracker: An instance of Progress to track the restore process.
        """
        with gzip.open(file, "r") as dump:
            self._restore_buffer(tracker, dump)

    def _restore_bzip(self, file: Path, tracker: progress.Progress):
        """Restore a database from a bzip2 archive containing a dump file and optionally a filestore.
        :param file: The path to the bzip2 archive.
        :param tracker: An instance of Progress to track the restore process.
        """
        with bz2.open(file, "rb") as dump:
            self._restore_buffer(tracker, dump)

    def _restore_sql(self, file: Path, tracker: progress.Progress):
        """Restore a database from a plaintext SQL dump file.
        :param file: The path to the dump file.
        :param tracker: An instance of Progress to track the restore process.
        """
        with open(file, "rb") as dump:
            self._restore_buffer(tracker, dump)

    def _restore_dump(self, file: Path, tracker: progress.Progress):
        """Restore a database from a dump file generated with `pg_dump`.
        :param file: The path to the dump file.
        :param tracker: An instance of Progress to track the restore process.
        """
        self._restore_buffered_sql(tracker, open(file, "rb"), file.stat().st_size, "dump")

    @ensure_connected
    def unaccent(self):
        """Install the unaccent extension on the database."""
        unaccent_queries = [
            "CREATE SCHEMA IF NOT EXISTS unaccent_schema",
            "CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA unaccent_schema",
            "COMMENT ON EXTENSION unaccent IS 'text search dictionary that removes accents'",
            """
            DO $$
            BEGIN
                CREATE FUNCTION public.unaccent(text)
                    RETURNS text
                    LANGUAGE sql IMMUTABLE
                    AS $_$
                        SELECT unaccent_schema.unaccent('unaccent_schema.unaccent', $1)
                    $_$;
                EXCEPTION
                    WHEN duplicate_function
                    THEN null;
            END; $$
            """,
            "GRANT USAGE ON SCHEMA unaccent_schema TO PUBLIC",
        ]

        res: bool = True

        for query in unaccent_queries:
            res &= self.query(query)

        return res

    @ensure_connected
    def table_exists(self, table: str) -> bool:
        """Check if a table exists in the database."""
        return self.connector.table_exists(table)

    @ensure_connected
    def create_table(self, table: str, columns: Mapping[str, str]):
        """Create a table in the database."""
        return self.connector.create_table(table, columns)

    @ensure_connected
    def query(self, query: str):
        """Execute a query on the database."""
        return self.connector.query(query)
