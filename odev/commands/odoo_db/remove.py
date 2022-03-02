"""Removes a local database from PostgreSQL and deletes its filestore."""

import os
import shutil
from argparse import Namespace

from odev.constants import DB_TEMPLATE_SUFFIX, DEFAULT_DATABASE
from odev.exceptions import CommandAborted, InvalidDatabase, RunningOdooDatabase
from odev.structures import commands
from odev.utils import logging


_logger = logging.getLogger(__name__)


class RemoveCommand(commands.LocalDatabaseCommand):
    """
    Drop a local database in PostgreSQL and delete its Odoo filestore on disk.
    """

    name = "remove"
    aliases = ["rm", "del"]
    keep_template = False

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.keep_template = "keep_template" in args

    def run(self):
        """
        Deletes an existing local database and its filestore.
        """

        if not self.db_exists_all():
            raise InvalidDatabase(f"Database {self.database} does not exist")

        if self.db_runs():
            raise RunningOdooDatabase(f"Database {self.database} is running, please shut it down and retry")

        version = self.db_version_clean()
        odoo_path = self.config["odev"].get("paths", "odoo")
        venv_path = os.path.join(odoo_path, version, self.database)

        if os.path.isdir(venv_path) and self.database != "venv":
            _logger.info(f"Deleted specific virtual env {self.database}")
            shutil.rmtree(venv_path)

        keep_filestore = self.keep_template
        dbs = [self.database]
        queries = [f"""DROP DATABASE "{self.database}";"""]
        info_text = f"Deleting PSQL database {self.database}"
        template_db_name = f"{self.database}{DB_TEMPLATE_SUFFIX}"

        if not self.keep_template and self.db_exists(template_db_name):
            _logger.warning(f"You are about to delete the database template {template_db_name}")

            confirm = _logger.confirm(f"Delete database template `{template_db_name}` ?")
            if confirm:
                queries.append(f"""DROP DATABASE "{template_db_name}";""")
                dbs.append(template_db_name)
                info_text += " and his template"

            keep_filestore = not confirm

        with_filestore = " and his filestore" if not keep_filestore else ""

        _logger.warning(
            f"You are about to delete the database {self.database}{with_filestore}." " This action is irreversible."
        )

        if not _logger.confirm(f"Delete database `{self.database}`{with_filestore}?"):
            raise CommandAborted()

        _logger.info(info_text)
        # We need two calls as Postgres will embed those two queries inside a block
        # https://github.com/psycopg/psycopg2/issues/1201
        result = None

        for query in queries:
            result = self.run_queries(query, database=DEFAULT_DATABASE)

        if not result or self.db_exists_all():
            return 1

        _logger.info("Deleted database")

        if not keep_filestore:
            filestore = self.db_filestore()

            if not os.path.exists(filestore):
                _logger.info("Filestore not found, no action taken")
            else:
                try:
                    _logger.info(f"Attempting to delete filestore in `{filestore}`")
                    shutil.rmtree(filestore)
                except Exception as exc:
                    _logger.warning(f"Error while deleting filestore: {exc}")
                else:
                    _logger.info("Deleted filestore from disk")

        for db in dbs:
            if db in self.config["databases"]:
                self.config["databases"].delete(db)

        return 0
