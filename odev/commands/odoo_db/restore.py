"""Restores an Odoo dump file to a local database with its filestore."""

import os
import re
import shutil
import subprocess
import time
import zipfile
from argparse import Namespace
from functools import partial, wraps
from io import UnsupportedOperation
from pathlib import Path
from typing import IO, Callable, Tuple
from zipfile import ZipFile

import enlighten

from odev.commands.odoo_db import clean, remove
from odev.constants import DB_TEMPLATE_SUFFIX
from odev.exceptions import RunningOdooDatabase
from odev.structures import commands, database
from odev.utils import logging


_logger = logging.getLogger(__name__)


BUFFER_SIZE = 64 * 1024

BAR_FORMAT = (
    "{desc}{desc_pad}{percentage:3.0f}%|{bar}| "
    "{count:!.2j}{unit} / {total:!.2j}{unit} [{elapsed}<{eta}, {rate:!.2j}{unit}/s]"
)


def restore_subprocess(fnc: Callable[..., Tuple[Callable[[], IO], int, str]]):
    @wraps(fnc)
    def wrapper(*args):
        database = args[0]
        _logger.info(f"Importing SQL data to database {database}")
        file_loader, total_size, commandline = fnc(*args)
        with file_loader() as fp:
            try:
                fp.fileno()  # ok to pass file descriptor
                stdin = fp
            except UnsupportedOperation:
                stdin = subprocess.PIPE
            # TODO: pipe stdout and show last line in statusbar?
            with subprocess.Popen(commandline, shell=True, stdin=stdin, stdout=subprocess.DEVNULL) as proc:
                with enlighten.get_manager(set_scroll=False) as manager, manager.counter(
                    total=float(total_size),
                    desc="restoring",
                    unit="B",
                    bar_format=BAR_FORMAT,
                    leave=False,
                ) as pbar:
                    last_pos: int = 0
                    while proc.poll() is None:
                        if stdin is subprocess.PIPE:
                            proc.stdin.write(fp.read(BUFFER_SIZE))
                        else:
                            time.sleep(0.1)
                        pos: int = fp.tell()
                        pbar.update(float(pos - last_pos))
                        last_pos = pos
                        if pos >= total_size:
                            if stdin is subprocess.PIPE:
                                proc.stdin.close()
                            break
                if proc.poll() is None:
                    _logger.info("Waiting for SQL data import to finish...")
                    proc.wait()
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(returncode=proc.returncode, cmd=commandline)

    return wrapper


def get_dump_loader(dump_path: str) -> Callable[[], IO]:
    return partial(open, dump_path, "rb", buffering=BUFFER_SIZE)


@restore_subprocess
def pg_restore(database: str, dump_path: str) -> Tuple[Callable[[], IO], int, str]:
    return get_dump_loader(dump_path), os.path.getsize(dump_path), f'pg_restore -d "{database}"'


@restore_subprocess
def psql_plain(database: str, sql_file: str) -> Tuple[Callable[[], IO], int, str]:
    return get_dump_loader(sql_file), os.path.getsize(sql_file), f'psql "{database}"'


@restore_subprocess
def psql_gz(database: str, dump_file: str) -> Tuple[Callable[[], IO], int, str]:
    return get_dump_loader(dump_file), os.path.getsize(dump_file), f'zcat - | psql "{database}"'


@restore_subprocess
def psql_zip(database: str, dumpzip: zipfile.ZipFile, member: str) -> Tuple[Callable[[], IO], int, str]:
    return partial(dumpzip.open, member, "r", force_zip64=True), dumpzip.getinfo(member).file_size, f'psql "{database}"'


class RestoreCommand(database.DBExistsCommandMixin, commands.TemplateCreateDBCommand):
    """
    Restore an Odoo dump file to a local database and import its filestore
    if present. '.sql', '.dump' and '.zip' files are supported.
    """

    name = "restore"
    arguments = [
        {
            "aliases": ["dump"],
            "metavar": "PATH",
            "help": "Path to the dump file to import to the database",
        },
        {
            "aliases": ["--no-clean"],
            "dest": "no_clean",
            "action": "store_true",
            "help": "Do not attempt to run the `clean` command on the database (useful for upgrades)",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.dump_path = args.dump
        self.run_clean = not args.no_clean

    def run(self):
        """
        Restores a dump file to a local database.
        """

        if self.db_runs():
            raise RunningOdooDatabase(f"Database {self.database} is running, please shut it down and retry")

        if not os.path.isfile(self.dump_path):
            raise FileNotFoundError(f"File {self.dump_path} does not exists")

        _, tail = os.path.split(self.dump_path)
        _, ext = os.path.splitext(tail)

        if not ext:
            raise ValueError(f"File `{self.dump_path}` has no extension, couldn't guess what to do...")

        _logger.info(f"Restoring dump file `{self.dump_path}` to database {self.database}")
        _logger.warning("This may take a while, please be patient...")

        if ext == ".dump":
            pg_restore(self.database, self.dump_path)
        elif ext == ".sql":
            psql_plain(self.database, self.dump_path)
        elif ext == ".gz":
            psql_gz(self.database, self.dump_path)
        elif ext == ".zip":
            self.handle_zipped_dump()
        else:
            raise ValueError(f"Unrecognized extension `{ext}` for file {self.dump_path}")

        if self.run_clean:
            clean.CleanCommand.run_with(**self.args.__dict__)

        dbs = [self.database]

        if self.args.create_template:
            template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"

            q = f"A template with the same name `{template_db_name}` already exist do you want to delete it ?"
            if self.db_exists(template_db_name) and _logger.confirm(q):
                remove.RemoveCommand.run_with(**dict(self.args.__dict__, database=template_db_name, keep_template=True))

            _logger.info(f"Creating template : {template_db_name}")
            self.run_queries(f'CREATE DATABASE "{template_db_name}" WITH TEMPLATE "{self.database}"')
            dbs.append(f"{template_db_name}")

        db_config = self.config["databases"]
        version = self.db_base_version(self.database)
        version_clean = self.db_version_clean(self.database)
        enterprise = "enterprise" if self.db_enterprise(self.database) else "standard"

        for db in dbs:
            db_config.set(db, "version", version)
            db_config.set(db, "version_clean", version_clean)
            db_config.set(db, "enterprise", enterprise)

        db_config.save()

        return 0

    def handle_zipped_dump(self):
        with ZipFile(self.dump_path, "r") as dumpzip:
            infolist = dumpzip.infolist()
            members = {entry.filename for entry in infolist}

            if "dump.sql" not in members:
                raise ValueError(f"{self.dump_path} contains no `dump.sql`")
            psql_zip(self.database, dumpzip, "dump.sql")

            filestore_re = re.compile(r"^filestore/(.+)$")
            filestore_infos = [info for info in infolist if filestore_re.match(info.filename)]
            if filestore_infos:
                filestores_root = Path.home() / ".local/share/Odoo/filestore"
                filestore_path = filestores_root / self.database
                _logger.info(f"Filestore detected, installing to {filestore_path}")

                if os.path.isdir(filestore_path):
                    _logger.warning(f"A filestore already exists at `{filestore_path}`")

                    actions = set("OMC")
                    choice = False
                    while not choice and choice not in actions:
                        try:
                            choice = _logger.ask("[O]verwrite / [M]erge / [C]ancel ").capitalize()[0]
                        except ValueError:
                            continue

                    if choice == "O":
                        _logger.warning("Deleting existing filestore directory")
                        shutil.rmtree(filestore_path)
                    elif choice == "M":
                        _logger.warning("Merging existing filestore directory")
                    elif choice == "C":
                        _logger.warning("Not touching filestore, finishing")
                        return

                for zipinfo in filestore_infos:
                    # member is saved w/ full filepath, modify it
                    m = filestore_re.match(zipinfo.filename)
                    assert m is not None
                    zipinfo.filename = m.group(1)
                    # filestore saves using sha256 as filename
                    # if exists, don't extract
                    if (filestore_path / zipinfo.filename).exists():
                        continue
                    dumpzip.extract(zipinfo, path=filestore_path)
