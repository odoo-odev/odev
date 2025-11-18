"""PostgreSQL database class."""

import bz2
import gzip
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Generator, Mapping
from datetime import datetime
from functools import cached_property
from pathlib import Path
from subprocess import PIPE, Popen
from time import sleep
from types import FrameType
from typing import (
    IO,
    ClassVar,
    Literal,
    Union,
    cast,
)
from zipfile import ZipFile

from packaging.version import Version

from odev.common import bash, progress, string
from odev.common.connectors import GitWorktree, PostgresConnector
from odev.common.databases import Branch, Database, Filestore, Repository
from odev.common.databases.base import DatabaseInfoSection
from odev.common.errors import OdevError
from odev.common.logging import logging
from odev.common.mixins import PostgresConnectorMixin, ensure_connected
from odev.common.odoobin import OdoobinProcess
from odev.common.python import PythonEnv
from odev.common.signal_handling import capture_signals
from odev.common.thread import Thread
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


ARCHIVE_DUMP = "dump.sql"
ARCHIVE_FILESTORE = "filestore/"

SQL_DUMP_IGNORE_LINES_NUMBER = 100
SQL_DUMP_RESTRICT_BACKPORTS = [
    Version("13.22"),
    Version("14.19"),
    Version("15.14"),
    Version("16.10"),
    Version("17.6"),
    Version("18.0"),
]

NEUTRALIZE_BEFORE_ODOO_VERSION = OdooVersion("15.0")


class LocalDatabase(PostgresConnectorMixin, Database):
    """Class for manipulating PostgreSQL (local) databases."""

    connector: PostgresConnector | None = None
    """The PostgreSQL connector of the database."""

    _whitelisted: bool = False
    """Whether the database is whitelisted and should not be removed automatically."""

    _filestore: Filestore | None = None
    """The filestore of the database."""

    _repository: Repository | None = None
    """The repository containing custom code for the database."""

    _branch: Branch | None = None
    """The branch of the repository containing custom code for the database."""

    _platform: ClassVar[Literal["local"]] = "local"  # type: ignore [assignment]
    """The platform on which the database is running."""

    _platform_display: ClassVar[str] = "Local"
    """The display name of the platform on which the database is running."""

    _venv: PythonEnv | None = None
    """The path to the virtual environment of the database."""

    _worktree: str | None = None
    """The name of the worktree used to run the database."""

    _process: OdoobinProcess | None = None
    """The Odoo process running the database."""

    def __init__(self, name: str):
        """Initialize the database.
        :param name: The name of the database.
        """
        super().__init__(name)

        if self.is_odoo:
            info = self.store.databases.get(self)
            self.whitelisted = info is not None and info.whitelisted

    def __enter__(self):
        self.connector = self.psql(self.name).__enter__()  # type: ignore [assignment]
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
    def venv(self) -> PythonEnv:
        if self._venv is None:
            info = self.store.databases.get(self)

            if info is None:
                if self.version is None:
                    return PythonEnv()

                self._venv = PythonEnv(str(self.version))
            else:
                self._venv = PythonEnv(info.virtualenv)

        return self._venv

    @venv.setter
    def venv(self, value: Union["str", Path, PythonEnv]):
        """Set the virtualenv path of the database."""
        if isinstance(value, (str, Path)):
            value = PythonEnv(value)

        self._venv = value
        self.store.databases.set(self)

    @property
    def worktree(self) -> str | None:
        if self._worktree is None:
            info = self.store.databases.get(self)

            if info is not None:
                self._worktree = info.worktree

        return self._worktree

    @worktree.setter
    def worktree(self, value: str):
        """Set the worktree name of the database."""
        self._worktree = value
        self.store.databases.set(self)

    @property
    def worktrees(self) -> Generator[GitWorktree, None, None]:
        """Odoo worktrees for running the database."""
        if self.process:
            yield from self.process.odoo_worktrees

    @property
    def version(self) -> OdooVersion | None:  # type: ignore [override]
        if not self.is_odoo:
            return None

        with self:
            result = self.connector.query(
                """
                SELECT latest_version
                FROM ir_module_module
                WHERE name = 'base'
                LIMIT 1
                """
            )

        if result and not isinstance(result, bool):
            version = result[0][0]

            if version is not None:
                return OdooVersion(version)

        return OdooVersion("master")

    @cached_property
    def edition(self) -> Literal["community", "enterprise"] | None:  # type: ignore [override]
        if not self.is_odoo:
            return None

        with self:
            result = cast(PostgresConnector, self.connector).query(
                """
                SELECT true
                FROM ir_module_module
                WHERE license LIKE 'OEEL-%'
                    AND state = 'installed'
                LIMIT 1
                """
            )

        return "enterprise" if result and result is not True and result[0][0] else "community"

    @property
    def filestore(self) -> Filestore:
        if self._filestore is None:
            path: Path = Path.home() / ".local/share/Odoo/filestore/" / self.name
            size: int = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            self._filestore = Filestore(path=path, size=size)

        return self._filestore

    @property
    def url(self) -> str | None:
        if not self.is_odoo or self.process is None:
            return None

        return (self.process.is_running and f"http://localhost:{self.process.rpc_port}") or None

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
        return cast(int, result[0][0]) if result and result is not True else 0

    @property
    def expiration_date(self) -> datetime | None:
        if not self.is_odoo:
            return None

        with self:
            result = cast(PostgresConnector, self.connector).query(
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
    def uuid(self) -> str | None:
        if not self.is_odoo:
            return None

        with self:
            result = cast(PostgresConnector, self.connector).query(
                """
                SELECT value
                FROM ir_config_parameter
                WHERE key = 'database.uuid'
                LIMIT 1
                """
            )

        return None if not result or isinstance(result, bool) else result[0][0]

    @property
    def last_date(self) -> datetime | None:
        """The last date the database was used or accessed."""
        last_access = self.last_access_date
        last_usage = self.last_usage_date

        if last_access and last_usage:
            return max(last_access, last_usage)

        return last_access or last_usage

    @property
    def last_usage_date(self) -> datetime | None:
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
            return None if not result or isinstance(result, bool) else result[0][0]

    @property
    def last_access_date(self) -> datetime | None:
        if not self.is_odoo:
            return None

        with self:
            result = cast(PostgresConnector, self.connector).query(
                """
                SELECT create_date
                FROM res_users_log
                ORDER BY create_date DESC
                LIMIT 1
                """
            )

        return None if not result or isinstance(result, bool) else result[0][0]

    @property
    def exists(self) -> bool:
        """Check if the database exists."""
        with self.psql() as psql:
            return bool(psql.database_exists(self.name))

    @property
    def running(self) -> bool:
        """Check if the database is running."""
        return self.process is not None and self.process.is_running

    @property
    def process(self) -> OdoobinProcess | None:
        if self._process is None and self.is_odoo:
            self._process = self._get_process_instance()

        return self._process

    @process.setter
    def process(self, value: OdoobinProcess | None):
        """Set the Odoo process of the database."""
        self._process = value

    @property
    def repository(self) -> Repository | None:
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
    def branch(self) -> Branch | None:
        if self.repository is None:
            return None

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
        return not self.is_odoo or (info is not None and info.whitelisted)

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
    def installed_modules(self) -> list[str]:
        """List modules that are currently installed on the database."""
        modules: list[tuple[str]] = self.query(
            """
            SELECT name
            FROM ir_module_module
            WHERE state IN ('installed', 'to upgrade', 'to remove');
            """
        )

        return [module[0] for module in modules]

    def _get_process_instance(self) -> OdoobinProcess:
        """Get the Odoo process for the database."""
        return OdoobinProcess(
            self,
            (self.venv and self.venv.path.name) or str(self.version),
            self.worktree or (str(self.version) if self.version else None),
            self.version,
        )

    def create(self, template: str | None = None) -> bool:
        """Create the database.

        :param template: The name of the template to copy.
        """
        with self.psql() as psql:
            created = psql.create_database(self.name, template=template)

        if created and self.is_odoo:
            self.store.databases.set(self)

        return created

    def drop(self) -> bool:
        shutil.rmtree(self.filestore.path, ignore_errors=True)

        if isinstance(self.connector, PostgresConnector):
            self.connector.disconnect()

        with self.psql() as psql:
            deleted = psql.drop_database(self.name)

        if deleted:
            self.store.databases.delete(self)

        return deleted

    def neutralize(self):
        """Neutralize the database."""
        max_retries = 5

        with self.connector.nocache():
            # Artificially wait for SQL transaction to be committed and for the process to be ready
            # before running the neutralize command
            # This is not clean but it works, I guess
            while (not self.process or not self.version) and (retries := 0) < max_retries:
                retries += 1
                sleep(0.2)

        admin = self._db_user_admin()

        if not admin["active"]:
            logger.warning(
                "The administrator account is archived in this database, this will cause issues during neutralization\n"
                "Reactivating the administrator account now, please verify the database configuration "
                "after neutralization and compare it to the original database"
            )
            self.query(
                f"""
                UPDATE res_users
                SET active = true
                WHERE id = {admin["id"]}
                """
            )

        self.process.with_venv(str(self.version))
        self.process.with_worktree(str(self.version))

        if self.process.supports_subcommand("neutralize"):
            self.process.run(["-d", self.name], subcommand="neutralize")
            self.console.print()

        installed_modules: set[str] = set(self.installed_modules) & {
            path.name for path in self.process.additional_addons_paths
        }
        scripts: list[Path] = [self.odev.static_path / "neutralize-pre.sql"]

        with progress.spinner(f"Looking up neutralization scripts in {len(installed_modules)} installed modules"):
            for addon in self.process.additional_addons_paths:
                for module in installed_modules:
                    neutralize_path: Path = addon / module / "data" / "neutralize.sql"

                    if neutralize_path.is_file():
                        scripts.append(neutralize_path)

        scripts.append(self.odev.static_path / "neutralize-post.sql")

        if self.version < NEUTRALIZE_BEFORE_ODOO_VERSION:
            scripts.append(self.odev.static_path / "neutralize-post-before-15.0.sql")

        tracker = progress.Progress()

        task = tracker.add_task(f"Running {len(scripts)} neutralization scripts", total=len(scripts))
        tracker.start()

        for python_file in scripts:
            tracker.update(task, advance=1, description=self.console.render_str(f"Running {python_file.as_posix()}"))  # type: ignore [attr-defined]
            self.query(python_file.read_text())

        tracker.stop()

    def dump(self, filestore: bool = False, path: Path | None = None) -> Path:
        if path is None:
            path = self.odev.dumps_path

        path.mkdir(parents=True, exist_ok=True)
        filename = self._get_dump_filename(filestore, suffix="neutralized" if self.neutralized else None)
        file = path / filename

        if file.exists() and not self.console.confirm(f"File {file} already exists. Overwrite it?"):
            return file

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
                    temp_directory_path = Path(temp_directory)
                    temp_file = temp_file.rename(temp_directory_path / "dump.sql")
                    shutil.copytree(self.filestore.path, temp_directory_path / "filestore")
                    shutil.make_archive((file.parent / file.stem).as_posix(), "zip", temp_directory_path)

        return file

    def restore(self, file: Path):
        tracker = progress.Progress(download=True)

        def signal_handler_progress(
            signal_number: int,
            frame: FrameType | None = None,
            message: str | None = None,
        ):
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
                logger.error(f"Unrecognized extension {file.suffix!r} for dump {file}")

        tracker.stop()

        if self.connector is not None:
            self.connector.invalidate_cache()

    def _restore_zip_filestore(self, tracker: progress.Progress, archive: ZipFile) -> Thread | None:
        """Restore the filestore from a zip archive.
        :param archive: The archive to restore the filestore from.
        :param tracker: An instance of Progress to track the restore process.
        """
        re_filestore_file = re.compile(rf"^{ARCHIVE_FILESTORE}(?P<dirname>[\da-f]{{2}})/(?P<filename>[\da-f]{{40}})$")
        info: list[tuple[re.Match[str], int]] = []

        for archive_info in archive.filelist:
            file_match = re_filestore_file.match(archive_info.filename)

            if file_match:
                info.append((file_match, archive_info.file_size))

        if not info:
            logger.debug("No filestore found in archive")
            return None

        logger.debug("Filestore found in archive, restoring")

        if self.filestore.path.exists():
            logger.warning(f"A filestore already exists for database {self.name!r}")
            overwrite_mode = cast(
                Literal["overwrite", "merge", "keep"],
                self.console.select(
                    "Overwrite the existing filestore?",
                    default="overwrite",
                    choices=[
                        ("overwrite", "Remove existing and overwrite with dump"),
                        ("merge", "Merge dump into existing filestore"),
                        ("keep", "Keep existing filestore"),
                    ],
                ),
            )

            if overwrite_mode == "keep":
                logger.debug("Keeping existing filestore")
                return None

            tracker.start()

            if overwrite_mode == "overwrite":
                shutil.rmtree(self.filestore.path)

        thread = Thread(target=self._restore_zip_filestore_threaded, args=(tracker, archive, info))
        thread.start()
        return thread

    def _restore_zip_filestore_threaded(
        self,
        tracker: progress.Progress,
        archive: ZipFile,
        info: list[tuple[re.Match[str], int]],
    ):
        """Thread to monitor the restore process of a zipped dump file and update the progress tracker.
        :param tracker: An instance of Progress to track the restore process.
        :param archive: The archive to restore the filestore from.
        :param info: A list of tuples containing the filestore file path and size.
        """
        filestore_size: int = sum(size for _, size in info)
        task_id = tracker.add_task("Extracting filestore from archive", total=filestore_size)
        tracker.start_task(task_id)
        tracker.start()

        invalid_blocks: int = 0
        max_invalid_blocks: int = 10

        for match, size in info:
            dirname: str = match.group("dirname")
            filename: str = match.group("filename")
            filepath = Path(dirname) / filename
            filestore_file_path: Path = self.filestore.path / filepath

            if not filestore_file_path.exists():
                try:
                    archive.getinfo(match.string).filename = filepath.as_posix()
                    archive.extract(match.string, self.filestore.path)
                except RuntimeError as ex:
                    logger.debug(f"Failed to extract filestore file {filepath.as_posix()}: {ex}")

                    if invalid_blocks <= max_invalid_blocks and "invalid stored block lengths" in str(ex):
                        invalid_blocks += 1
                        continue

                    if invalid_blocks:
                        logger.error(f"{invalid_blocks} filestore files failed to extract due to corrupted archive")

                        if sys.version_info <= (3, 12):
                            logger.warning(
                                "This could be due to a known limitation of python's zipfile module, "
                                "consider running odev with python 3.13+"
                            )

                        raise OdevError("Aborting") from ex

                    raise

            tracker.update(task_id, advance=size)

        logger.info(f"Extracted filestore to {self.filestore.path}")

        if invalid_blocks:
            logger.warning(f"{invalid_blocks} filestore files failed to extract due to corrupted archive")

        tracker.remove_task(task_id)

    def _restore_buffered_sql(
        self,
        tracker: progress.Progress,
        dump: gzip.GzipFile | bz2.BZ2File | IO[bytes],
        bytes_count: int,
        mode: Literal["sql", "dump"] = "sql",
        fast_mode: bool = True,
    ) -> Thread:
        """Restore SQL data from a buffered dump file.
        :param tracker: An instance of Progress to track the restore process.
        :param dump: The dump file to restore SQL data from.
        :param bytes_count: The total number of bytes to track.
        :param mode: The mode to use when restoring the dump, either `sql` or `dump`.
        :param fast_mode: Whether to run the restore in fast mode.
        """
        if mode == "sql":
            self._buffered_sql_check_restrict(dump)
            self._buffered_sql_enable_extensions(dump)
        elif mode == "dump":
            self.unaccent()

        command = self._buffered_sql_restore_command(mode=mode, fast_mode=fast_mode)

        # Adding 1 to the bytes count so that the progress bar doesn't reach 100%
        # until the process is complete and the last buffered line has been processed
        extract_task_id = tracker.add_task("Restoring dump from archive", total=bytes_count)
        tracker.start()

        psql_process: Popen[bytes] = Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=-1)  # noqa: S602
        thread = Thread(target=self._restore_zip_sql_threaded, args=(psql_process,))
        thread.start()

        try:
            for line in dump:
                psql_process.stdin.write(line)
                tracker.update(extract_task_id, advance=len(line))

        except BrokenPipeError as error:
            # Close the buffered writer, avoid BrokenPipe errors
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, psql_process.stdin.fileno())
            os.close(devnull)

            # Reset the tracker
            tracker.remove_task(extract_task_id)
            tracker.stop()
            self.console.clear_line()

            logger.error(
                "Failed to restore dump, the psql process exited unexpectedly with error:\n"
                + psql_process.stderr.read().decode()
            )

            if fast_mode:
                dump.seek(0)
                logger.warning("Retrying in degraded mode (slower and ignoring errors)")
                return self._restore_buffered_sql(tracker, dump, bytes_count, mode, fast_mode=False)

            if mode == "sql":
                odev_psql_version = OdoobinProcess.get_psql_version()
                dump_psql_version = re.search(
                    r"Dumped from database version (\d+\.\d+)", dump.read(4000).decode()
                ).group(1)
                logger.warning(
                    "This could be a PostgreSQL version mismatch between the dump and the installed psql client:\n"
                    f"- Dump version:  {dump_psql_version}\n"
                    f"- Local version: {odev_psql_version}\n"
                )

                if Version(dump_psql_version) > odev_psql_version:
                    logger.warning("Consider upgrading your local PostgreSQL installation")

            raise OdevError("Restore aborted") from error

        psql_process.stdin.close()
        thread.join()

        if psql_process.returncode or (errors := psql_process.stderr.read().decode().replace("\n" * 3, "\n")):
            logger.error(f"Errors occurred during the restore process:\n{errors}")

        return thread

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
                logger.error(
                    f"Invalid dump file {file.as_posix()}, "
                    f"missing {string.stylize(f'{ARCHIVE_DUMP!r}', 'color.cyan')} file"
                )
                return

            threads: list[Thread] = []

            if ARCHIVE_FILESTORE in archive.namelist():
                threads.append(self._restore_zip_filestore(tracker, archive))

            neuter_filestore = None in threads

            with archive.open(ARCHIVE_DUMP) as dump:
                threads.append(self._restore_buffered_sql(tracker, dump, archive.getinfo(dump.name).file_size))

            [thread.join() for thread in threads if thread is not None and thread.is_alive()]

            if neuter_filestore:
                self.neuter_filestore()
                logger.info("Neutered filestore")

            tracker.stop()

    def _restore_buffer(self, tracker: progress.Progress, dump: gzip.GzipFile | bz2.BZ2File | IO[bytes]):
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
        with file.open("rb") as dump:
            self._restore_buffered_sql(tracker, dump, file.stat().st_size, "dump")

    def _buffered_sql_check_restrict(self, dump: gzip.GzipFile | bz2.BZ2File | IO[bytes]):
        """Ensure the dump can be restored on the current version of PostgreSQL.

        :param dump: The dump file to restore SQL data from.
        """
        dump.seek(0)

        if not re.match(r"^\\restrict .*", dump.read(4000).decode()):
            dump.seek(0)
            return

        odev_psql_version = OdoobinProcess.get_psql_version()
        matching_psql_version = next(
            (version for version in SQL_DUMP_RESTRICT_BACKPORTS if version.major == odev_psql_version.major),
            None,
        )

        if (
            not matching_psql_version and odev_psql_version.major >= SQL_DUMP_RESTRICT_BACKPORTS[-1].major
        ) or matching_psql_version.minor <= odev_psql_version.minor:
            supports_restrict = True
        else:
            supports_restrict = False

        if not supports_restrict:
            logger.error("PostgreSQL '\\restrict' command is not supported, consider upgrading to a newer version")
            supported_versions = string.join_bullet(str(version) for version in SQL_DUMP_RESTRICT_BACKPORTS[::-1])
            logger.info(f"Current PostgreSQL version: {odev_psql_version}")
            logger.info(f"Supported PostgreSQL versions:\n{supported_versions}")
            raise OdevError("Restore aborted")

    def _buffered_sql_restore_command(self, mode: Literal["sql", "dump"], fast_mode: bool = True) -> str:
        """Build the command to restore SQL data from a buffered dump file.

        :param mode: Whether working with plain SQL files or a dump;
        :param fast_mode: Whether to run the restore in fast mode.
        :return: The command to restore SQL data from a buffered dump file.
        """
        command = "psql" if mode != "dump" else "pg_restore --disable-triggers --no-owner --no-privileges"
        command += f" --dbname {self.name}"

        if fast_mode:
            command += " --single-transaction"

            if mode == "sql":
                command += " -v ON_ERROR_STOP=1"

        return command

    def _buffered_sql_enable_extensions(self, dump: gzip.GzipFile | bz2.BZ2File | IO[bytes]):
        """Enable PostgreSQL extensions before restoring the dump.
        In the event the SQL dump doesn't set the unaccent function as immutable, we need to force it on the database
        ourselves. The creation of the function should be around the 50th line in the SQL file, we crawl up to
        the 100th to make sure we don't miss it.

        :param dump: The dump file to restore SQL data from.
        """
        for index, line in enumerate(dump):
            if index >= SQL_DUMP_IGNORE_LINES_NUMBER or "LANGUAGE sql IMMUTABLE" in line.decode():
                break
        else:
            self.unaccent()

        dump.seek(0)

    @ensure_connected
    def unaccent(self) -> bool:
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
    def pg_trgm(self) -> bool:
        """Install the pg_trgm extension on the database."""
        pg_trgm_query = "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"
        return self.query(pg_trgm_query)

    def pg_vector(self) -> bool:
        """Install the vector extension on the database.
        Try creating the extension through a regular query first, that will only work if the extension is whitelisted
        in `pgextwlist` or if the user is owner of the extension. If this fails, try enabling it as the `postgres`
        user.
        """
        pg_vector_query = "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"

        try:
            self.query(pg_vector_query)
        except RuntimeError:
            link = string.link(
                "pgextwlist",
                "https://github.com/dimitri/pgextwlist?tab=readme-ov-file#postgresql-extension-whitelist",
            )
            logger.error(
                "Failed to install 'pgvector' extension, please ensure it is installed on your system "
                f"and whitelisted with {link}"
            )
            return False

        return True

    @ensure_connected
    def neuter_filestore(self):
        """Neuter the filestore. Intended to be called only when the database is fetched without filestore.
        As there is a NOT NULL constraint on name and several ON DELETE RESTRICT constraints on the table, we set
        store_fname to ''.
        """
        neuter_fs_query = "UPDATE ir_attachment SET store_fname='' WHERE type='binary' AND store_fname IS NOT NULL"
        return self.query(neuter_fs_query)

    @ensure_connected
    def table_exists(self, table: str) -> bool:
        """Check if a table exists in the database."""
        return cast(PostgresConnector, self.connector).table_exists(table)

    @ensure_connected
    def create_table(self, table: str, columns: Mapping[str, str]):
        """Create a table in the database."""
        return cast(PostgresConnector, self.connector).create_table(table, columns)

    @ensure_connected
    def query(self, query: str):
        """Execute a query on the database."""
        return cast(PostgresConnector, self.connector).query(query)

    def _info_git(self) -> DatabaseInfoSection:
        return super()._info_git() | {
            worktree.path.name: f"{worktree.connector.name} ({worktree.branch or worktree.commit})"
            for worktree in self.worktrees
        }

    def _info_backend(self) -> DatabaseInfoSection:
        """Return information about the backend of the database."""
        return super()._info_backend() | {
            "date_usage": self.last_date.strftime("%Y-%m-%d %X") if self.last_date else "Never",
            "filestore": f"{self.filestore.path.name} ({self.filestore.path.as_posix()})",
            "venv": f"{self.venv} ({self.venv.path})" if not self.venv._global else "N/A",
            "worktree": f"{self.worktree} ({self.process.odoo_path.parent})" if self.process else "N/A",
            "pid": str(self.process.pid) if self.process and self.running else "N/A (not running)",
            "addons": string.join_bullet(list(map(str, self.process.addons_paths))) if self.process else "N/A",
        }

    def _db_user_admin(self) -> Mapping[str, str]:
        uid, active = self.query(
            """
            SELECT id, active
            FROM res_users
            WHERE id IN (
                SELECT res_id
                FROM ir_model_data
                WHERE model = 'res.users'
                    AND (module, name) = ('base', 'user_admin')
            )
            """
        )[0]

        return {"id": uid, "active": active}
