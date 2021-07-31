# -*- coding: utf-8 -*-

import os
import re
from abc import ABC
from argparse import ArgumentParser, Namespace
from pathlib import Path
import configparser

from psycopg2 import sql

from .. import utils
from ..cli import CliCommand
from ..psql import PSQL


class _NO_DB:
    """Sentinel object for root, using a class for better repr"""


NO_DB = _NO_DB()


re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
re_command = re.compile(r'([/.a-zA-Z0-9_-]+\/odoo-bin.*)$')
re_port = re.compile(r'(-p\s|--http-port=)([0-9]{1,5})')


class LocalDBCommand(CliCommand, ABC):

    options = []
    config = configparser.ConfigParser()
    config.read('%s/.config/odev/odev.cfg' % (str(Path.home())))
    config.sections()
    dbconfig = configparser.ConfigParser()
    dbconfig.read('%s/.config/odev/databases.cfg' % (str(Path.home())))
    dbconfig.sections()

    database_required = True
    odoo_databases = []

    @classmethod
    def prepare_arguments(cls, parser: ArgumentParser) -> None:
        super().prepare_arguments(parser)
        parser.add_argument(
            "database",
            nargs=None if cls.database_required else '?',
            help="Name of the local database",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        if args.database:
            utils.dbname_validate(args.database)
        self.database = args.database

    def _get_database(self, database=None):
        return database or self.database

    def run_queries(self, queries=None, database=None):
        """
        Runs a default subcommand.
        """
        database = self._get_database(database) if database is not NO_DB else None

        if queries:
            if not isinstance(queries, list):
                queries = [queries]

            with PSQL(database) as psql:
                result = psql.query(queries)

            last_query = queries[-1]
            if last_query:
                if isinstance(last_query, sql.Composed):
                    [last_query] = last_query.seq[:1]
                if isinstance(last_query, sql.SQL):
                    last_query = last_query.string
                if last_query.lower().strip().startswith("select"):
                    return result

        return True

    def db_list(self):
        """
        Lists names of local Odoo databases.
        """
        if self.odoo_databases:
            return self.odoo_databases

        with PSQL() as psql:
            result = psql.query(
                """
                SELECT datname FROM pg_database
                WHERE datistemplate = false AND datname != 'postgres'
                ORDER BY datname
                """
            )

        query = """SELECT id FROM ir_module_module WHERE name = 'base'"""
        odoo_databases = [
            database for [database] in result if self.run_queries(query, database=database)
        ]
        self.odoo_databases = odoo_databases
        return odoo_databases

    def db_list_all(self):
        """
        Lists names of all local databases.
        """
        with PSQL() as psql:
            result = psql.query("SELECT datname FROM pg_database ORDER by datname")
        return [database for [database] in result]

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

    def db_create(self, database=None, template=None):
        """
        Creates a new database in PostgreSQL, optionally using a template database
        """
        database = self._get_database(database)

        query = 'CREATE DATABASE {database}'
        query_kwargs = dict(database=sql.Identifier(database))

        if template:
            query += ' WITH TEMPLATE {template}'
            query_kwargs.update(template=sql.Identifier(template))

        query = sql.SQL(query).format(**query_kwargs)

        return self.run_queries(query, database=NO_DB)

    def db_drop(self, database=None):
        """
        Drops an existing PostgreSQL database
        """
        database = self._get_database(database)
        query = sql.SQL('DROP DATABASE {}').format(sql.Identifier(database))
        return self.run_queries(query, database=NO_DB)

    def db_rename(self, new_name, database=None):
        """
        Drops an existing PostgreSQL database
        """
        database = self._get_database(database)
        query = sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
            sql.Identifier(database), sql.Identifier(new_name)
        )
        return self.run_queries(query, database=NO_DB)

    def db_is_valid(self, database=None):
        """
        Checks whether the database both exists and is an Odoo database.
        """
        database = self._get_database(database)
        if not self.db_exists_all(database):
            raise Exception('Database \'%s\' does not exists' % (database))
        elif not self.db_exists(database):
            raise Exception('Database \'%s\' is not an Odoo database' % (database))

    def db_version(self, database=None):
        """
        Gets the version number of a database.
        """
        database = self._get_database(database)

        self.db_is_valid(database)

        with PSQL(database) as psql:
            [[result]] = psql.query(
                """
                SELECT latest_version FROM ir_module_module WHERE name = 'base'
                """
            )

        return result

    def db_version_clean(self, database=None):
        """
        Gets the version number of a database.
        """
        database = self._get_database(database)

        version = self.db_version(database)
        match = re_version.match(version)
        version = match.group(0)

        return version

    def db_version_full(self, database=None):
        """
        Gets the full version of the database.
        """
        database = self._get_database(database)

        version = self.db_version_clean(database)
        enterprise = self.db_enterprise(database)

        return 'Odoo %s (%s)' % (version, 'enterprise' if enterprise else 'standard')

    def db_enterprise(self, database=None):
        """
        Checks whether a database is running on the enterprise version of Odoo.
        """
        database = self._get_database(database)

        self.db_is_valid(database)

        with PSQL(database) as psql:
            result = psql.query(
                """
                SELECT TRUE FROM ir_module_module
                WHERE name LIKE '%enterprise' LIMIT 1
                """
            )

        return bool(result)

    def db_pid(self, database=None):
        """
        Gets the PID of a currently running database.
        """
        database = self._get_database(database)

        command = 'ps aux | grep -E "./odoo-bin\\s-d\\s%s\\s" | awk \'NR==1{print $2}\'' % (database)
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

        self.db_is_valid(database)

        if not self.db_runs(database):
            raise Exception('Database \'%s\' is not running' % (database))

        command = 'ps aux | grep -E "./odoo-bin\\s-d\\s%s\\s"' % (database)
        stream = os.popen(command)
        cmd = stream.read().strip()
        match = re_command.search(cmd)

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
            match = re_port.search(command)

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

        return 'http://localhost:%s/web' % (self.db_port(database))

    def db_filestore(self, database=None):
        """
        Returns the absolute path to the filestore of a given database.
        """
        database = self._get_database(database)
        return '%s/.local/share/Odoo/filestore/%s' % (str(Path.home()), database)

    def db_config(self, database=None, **values):
        """
        If `values` is set, saves new values to the configuration of a database.
        Otherwise fetches the configuration of a database if it exists.
        """
        database = self._get_database(database)

        if values:
            with open('%s/.config/odev/databases.cfg' % (str(Path.home())), 'w') as configfile:

                for key, value in values.items():
                    if not self.dbconfig.has_section(database):
                        self.dbconfig.add_section(database)

                    self.dbconfig.set(database, key, value)

                self.dbconfig.write(configfile)

        if self.dbconfig.has_section(database):
            return self.dbconfig[database]

        return None

    def db_config_get(self, database=None, key=None):
        """
        Fetches a single value from a database configuration file.
        """
        database = self._get_database(database)
        utils.require('key', key)

        self.db_is_valid(database)

        if self.dbconfig.has_section(database) and self.dbconfig.has_option(database, key):
            return self.dbconfig.get(database, key)

        return None

    def ensure_stopped(self, database=None):
        """
        Throws an error of the database is running.
        """
        database = self._get_database(database)

        self.db_is_valid(database)

        if self.db_runs(database):
            raise Exception('Database %s is running, please shut it down and retry' % (database))

    def ensure_running(self, database=None):
        """
        Throws an error of the database is not running.
        """
        database = self._get_database(database)

        self.db_is_valid(database)

        if not self.db_runs(database):
            raise Exception('Database %s is not running, please start it up and retry' % (database))
