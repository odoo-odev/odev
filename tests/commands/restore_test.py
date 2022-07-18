import os
import tempfile
from argparse import Namespace
from zipfile import ZipFile

import pytest

from odev.commands.odoo_db.restore import (
    RestoreCommand,
    pg_restore,
    psql_gz,
    psql_plain,
    psql_zip,
)
from odev.structures.commands import LocalDatabaseCommand


FILE_EXTS_TO_TEST = [".gz", ".zip", ".dump", ".sql"]


@pytest.fixture(autouse=True)
def no_psycopg(monkeypatch):
    def db_runs(*args, **kwargs):
        return False

    def db_exists_all(*args, **kwargs):
        return True

    monkeypatch.setattr(RestoreCommand, "db_runs", db_runs)
    monkeypatch.setattr(LocalDatabaseCommand, "db_exists_all", db_exists_all)


@pytest.fixture
def args():
    return Namespace(
        database="odev_test_database",
        dump="/path/to/dumpfile.fail_ext",
        assume_yes=True,
        assume_no=False,
        no_clean=True,
        log_level="WARNING",
        create_template=False,
    )


@pytest.fixture
def restore_command(args):
    return RestoreCommand(args)


def test_file_not_found(restore_command):
    with pytest.raises(FileNotFoundError):
        restore_command.run()


def test_raise_unrecognized(restore_command):
    with pytest.raises(ValueError), tempfile.TemporaryDirectory("odev_test") as temp_dir:
        _path, filename = os.path.split(restore_command.dump_path)
        filepath = os.path.join(temp_dir, filename)
        # probably not necessary
        with open(filepath, "b") as fp:
            fp.write(os.urandom(42))
        restore_command.dump_path = filepath

        restore_command.run()


def test_correct_output_command(args):
    file_ext_to_test_data = {
        ".zip": ("psql", psql_zip.__wrapped__),
        ".sql": ("psql", psql_plain.__wrapped__),
        ".gz": ("psql", psql_gz.__wrapped__),
        ".dump": ("pg_restore", pg_restore.__wrapped__),
    }
    filesize_answer = 42
    with tempfile.TemporaryDirectory(prefix="odev_tests") as temp_dir:
        for ext, (pipe_into_cmd_str, pipe_data) in file_ext_to_test_data.items():
            test_db_path = "odev_test_db"
            test_filename = "odev_test_dump" + ext

            if not ext == ".zip":
                filepath = os.path.join(temp_dir, test_filename)
                with open(filepath, "wb") as fp:
                    fp.write(os.urandom(filesize_answer))
                _file_loader, total_size, commandline = pipe_data(test_db_path, filepath)
            else:
                member = "dump.sql"
                zip_filepath = os.path.join(temp_dir, test_filename)
                with open(zip_filepath, "wb") as fp, ZipFile(fp, "w") as dumpzip:
                    dumpzip.writestr(member, os.urandom(filesize_answer))

                with ZipFile(zip_filepath, "r") as dumpzip:
                    _file_loader, total_size, commandline = pipe_data(test_db_path, dumpzip, member)

            assert pipe_into_cmd_str in commandline, f"should contain command {pipe_into_cmd_str}"
            assert total_size == filesize_answer, "answer should be 42"
