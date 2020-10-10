# -*- coding: utf-8 -*-

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


class SQL():

    database = 'template1'
    connection = None
    cursor = None

    def connect(self, database=database):
        """
        Connect to a local database and returns a cursor to the database.
        """

        if not database:
            database = self.database
        else:
            self.database = database

        self.connection = psycopg2.connect('dbname=%s' % (database))
        self.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        self.cursor = self.connection.cursor()

    def query(self, query):
        """
        Executes a query and returns its result.
        """

        try:
            self.cursor.execute(query)
            result = self.cursor.fetchall()
        except Exception:
            result = False

        return result

    def disconnect(self):
        """
        Closes the connection to a local database.
        """

        if self.cursor:
            self.cursor.close()

        if self.connection:
            self.connection.commit()
            self.connection.close()
