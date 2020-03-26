# -*- coding: utf-8 -*-

import os
import re
from pathlib import Path
import configparser

from .. import sql
from .. import utils

re_version = re.compile(r'^([a-z~0-9]+\.[0-9]+)')
re_command = re.compile(r'(\.\/odoo-bin.*)$')
re_port = re.compile(r'(-p\s|--http-port=)([0-9]{1,5})')


class Script():
    
    psql = sql.SQL()
    database = 'template1'
    options = []
    config = configparser.ConfigParser()
    config.read('/etc/odev/odev.cfg')
    config.sections()

    def run(self, database=database, queries=None):
        """
        Runs a default subcommand.
        """

        utils.require('database', database)

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

        query = 'SELECT datname FROM pg_database WHERE datistemplate = false AND datname != \'postgres\' ORDER by datname;'
        
        self.psql.connect(self.database)
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

        return odoo_databases

    def db_list_all(self):
        """
        Lists names of all local databases.
        """

        query = 'SELECT datname FROM pg_database ORDER by datname;'

        self.psql.connect(self.database)
        result = self.psql.query(query)
        self.psql.disconnect()

        databases = []

        for database in result:
            databases.append(database[0])

        return databases

    def db_exists(self, database):
        """
        Checks whether a database with the given name already exists and is an Odoo database.
        """

        utils.require('database', database)

        return database in self.db_list()

    def db_exists_all(self, database):
        """
        Checks whether a database with the given name already exists.
        """

        utils.require('database', database)

        return database in self.db_list_all()

    def db_valid(self, database):
        """
        Checks whether the database both exists and is an Odoo database.
        """

        utils.require('database', database)

        if not self.db_exists_all(database):
            raise Exception('Database \'%s\' does not exists' % (database))
        elif not self.db_exists(database):
            raise Exception('Database \'%s\' is not an Odoo database' % (database))

    def db_version(self, database):
        """
        Gets the version number of a database.
        """

        self.db_valid(database)

        query = 'SELECT latest_version FROM ir_module_module WHERE name = \'base\';'

        self.psql.connect(database)
        result = self.psql.query(query)[0][0]
        self.psql.disconnect()

        return result

    def db_version_clean(self, database):
        """
        Gets the version number of a database.
        """

        version = self.db_version(database)
        match = re_version.match(version)
        version = match.group(0)

        return version

    def db_version_full(self, database):
        """
        Gets the full version of the database.
        """
    
        version = self.db_version_clean(database)
        enterprise = self.db_enterprise(database)

        return 'Odoo %s (%s)' % (version, 'enterprise' if enterprise else 'standard')

    def db_enterprise(self, database):
        """
        Checks whether a database is running on the enterprise version of Odoo.
        """

        self.db_valid(database)

        query = 'SELECT TRUE FROM ir_module_module WHERE name LIKE \'%enterprise\' LIMIT 1;'

        self.psql.connect(database)
        result = self.psql.query(query)
        self.psql.disconnect()

        if not result:
            return False
        else:
            return True

    def db_pid(self, database):
        """
        Gets the PID of a currently running database.
        """

        self.db_valid(database)

        command = 'ps aux | grep -E \'\\./odoo-bin\\s-d\\s%s\\s\' | awk \'{print $2}\'' % (database)

        stream = os.popen(command)
        pid = stream.read().strip()

        return pid or None

    def db_runs(self, database):
        """
        Checks whether the database is currently running.
        """

        return bool(self.db_pid(database))

    def db_command(self, database):
        """
        Gets the command which has been used to start the Odoo server for a given database.
        """

        self.db_valid(database)

        if not self.db_runs(database):
            raise Exception('Database \'%s\' is not running' % (database))

        command = 'ps aux | grep -E \'\\./odoo-bin\\s-d\\s%s\\s\'' % (database)
        stream = os.popen(command)
        cmd = stream.read().strip()
        match = re_command.search(cmd)

        if not match:
            return None    
            
        cmd = match.group(0)
        
        return cmd or None

    def db_port(self, database):
        """
        Checks on which port the database is currently running.
        """

        port = None

        if self.db_runs(database):
            command = self.db_command(database)
            match = re_port.search(command)

            if match:
                port = match.group(2)
            else:
                port = 8069

        return port

    def db_url(self, database):
        """
        Returns the local url to the Odoo web application.
        """

        if not self.db_runs(database):
            return None

        return 'http://localhost:%s/web' % (self.db_port(database))

    def db_filestore(self, database):
        """
        Returns the absolute path to the filestore of a given database.
        """

        self.db_valid(database)

        return '%s/.local/share/Odoo/filestore/%s' % (str(Path.home()), database)
