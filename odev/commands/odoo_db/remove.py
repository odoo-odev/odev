"""Removes a local database from PostgreSQL and deletes its filestore."""

import os
import shutil
from argparse import Namespace

from odev.constants import DB_TEMPLATE_SUFFIX, DEFAULT_DATABASE, DEFAULT_VENV_NAME
from odev.exceptions import CommandAborted, InvalidDatabase, RunningOdooDatabase
from odev.structures import commands
from odev.utils import logging
from odev.utils.odoo import get_venv_path


_logger = logging.getLogger(__name__)


class RemoveCommand(commands.LocalDatabaseCommand):
    """
    Drop a local database in PostgreSQL and delete its Odoo filestore on disk.
    """

    name = "remove"
    aliases = ["rm", "del"]
    arguments = [
        {
            "aliases": ["--keep-filestore"],
            "action": "store_true",
            "help": "Do not delete the filestore for the db",
        },
        {
            "aliases": ["--keep-template"],
            "action": "store_true",
            "help": "Preserve the associated template db. Implies --keep-filestore",
        },
        {
            "aliases": ["--keep-venv"],
            "action": "store_true",
            "help": "Do not delete the db-specific venv, if any",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.keep_template: bool = args.keep_template
        self.keep_filestore: bool = self.keep_template or args.keep_filestore
        self.keep_venv = args.keep_venv

    def run(self):
        """
        Deletes an existing local database and its filestore.
        """

        if not self.db_exists_all():
            raise InvalidDatabase(f"Database {self.database} does not exist")

        if self.db_runs():
            raise RunningOdooDatabase(f"Database {self.database} is running, please shut it down and retry")

        is_odoo_db = self.is_odoo_db()
        version = self.db_version_clean()

        dbs = [self.database]
        queries = [f"""DROP DATABASE "{self.database}";"""]
        info_text = f"Dropping PSQL database {self.database}"
        template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"

        if not self.keep_template and self.db_exists(template_db_name):
            _logger.warning(f"You are about to delete the database template {template_db_name}")

            confirm = _logger.confirm(f"Delete database template `{template_db_name}` ?")
            if confirm:
                queries.append(f"""DROP DATABASE "{template_db_name}";""")
                dbs.append(template_db_name)
                info_text += " and his template"

        with_filestore = " and its filestore" if not self.keep_filestore else ""

        _logger.warning(
            f"You are about to delete the database {self.database}{with_filestore}. This action is irreversible."
        )

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

        if not self.keep_filestore:
            self.remove_filestore()

        if is_odoo_db and not self.keep_venv:
            self.remove_specific_venv(version)

        for db in dbs:
            if db in self.config["databases"]:
                self.config["databases"].delete(db)

        return 0

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
