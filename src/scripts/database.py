# -*- coding: utf-8 -*-

import os
import re
from abc import ABC
from argparse import ArgumentParser, Namespace
from pathlib import Path
import configparser

from .. import sql
from .. import utils
from ..cli import CliCommand


class _NO_DB:
    """Sentinel object for root, using a class for better repr"""


NO_DB = _NO_DB()


re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
re_command = re.compile(r'([/.a-zA-Z0-9_-]+\/odoo-bin.*)$')
re_port = re.compile(r'(-p\s|--http-port=)([0-9]{1,5})')


class LocalDBCommand(CliCommand, ABC):

    psql = sql.SQL()
    fallback_database = 'template1',
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
            nargs=1 if cls.database_required else '?',
            help="Name of the local database",
        )

    def __init__(self, args: Namespace):
        super().__init__(args)
        # TODO: depending on the action sanitize should fail instead
        self.database = utils.sanitize(args.database) if args.database else None

    def _get_database(self, database=None):
        if database is None:
            database = self.database
        if database is None or database is NO_DB:
            database = self.fallback_database
        return database

    def run_queries(self, queries=None, database=None):
        """
        Runs a default subcommand.
        """
        database = self._get_database(database)

        result = None

        if queries:

            if not isinstance(queries, list):
                queries = [queries]

            self.psql.connect(database)
            result = self.psql.query('; '.join(queries))
            self.psql.disconnect()

        if any(query.lower().startswith('select') for query in queries):
            return result
        else:
            return True

    def db_list(self):
        """
        Lists names of local Odoo databases.
        """
        if self.odoo_databases:
            return self.odoo_databases
        query = 'SELECT datname FROM pg_database WHERE datistemplate = false AND datname != \'postgres\' ORDER by datname;'

        self.psql.connect(self.fallback_database)
        result = self.psql.query(query)
        self.psql.disconnect()

        odoo_databases = []
        query = 'SELECT id FROM ir_module_module WHERE name = \'base\';'

        for database in result:
            self.psql.connect(database[0])
            result = self.psql.query(query)

            if result:
                odoo_databases.append(database[0])

            self.psql.disconnect()
        self.odoo_databases = odoo_databases
        return odoo_databases

    def db_list_all(self):
        """
        Lists names of all local databases.
        """

        query = 'SELECT datname FROM pg_database ORDER by datname;'

        self.psql.connect(self.fallback_database)
        result = self.psql.query(query)
        self.psql.disconnect()

        databases = []

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

        query = 'SELECT latest_version FROM ir_module_module WHERE name = \'base\';'

        self.psql.connect(database)
        result = self.psql.query(query)[0][0]
        self.psql.disconnect()

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

        query = 'SELECT TRUE FROM ir_module_module WHERE name LIKE \'%enterprise\' LIMIT 1;'

        self.psql.connect(database)
        result = self.psql.query(query)
        self.psql.disconnect()

        if not result:
            return False
        else:
            return True

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
