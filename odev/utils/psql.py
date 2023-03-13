from textwrap import dedent
from typing import Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from odev.constants import DEFAULT_DATABASE
from odev.exceptions.commands import InvalidQuery


class PSQL:

    fallback_database = DEFAULT_DATABASE

    def __init__(self, database=None):
        self.database = database or self.fallback_database
        self.connection: Optional[psycopg2.connection] = None
        self.cr = None

    def connect(self):
        """
        Connect to a local database and returns a cursor to the database.
        """
        self.connection = psycopg2.connect(database=self.database)
        self.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        self.cr = self.connection.cursor()

    def __enter__(self):
        self.connect()
        return self

    def query(self, queries):
        """
        Executes a query and returns its result.
        """
        if not isinstance(queries, list):
            queries = [queries]

        queries = [(query.as_string(self.cr) if isinstance(query, sql.Composable) else query) for query in queries]

        try:
            assert self.cr

            queries = [dedent(query).strip() for query in queries]
            for query in queries:
                assert isinstance(query, str)
                self.cr.execute(query)

            if any(str(query.strip()).lower().startswith("select") for query in queries):
                result = self.cr.fetchall()
            else:
                result = True
        except Exception as e:  # FIXME: Too broad and non-descriptive
            description = str(e).split("\n")[0]
            raise InvalidQuery(f"""Error while running SQL query: {description}""")

        return result

    def disconnect(self):
        """
        Closes the connection to a local database.
        """
        if self.cr:
            self.cr.close()
        if self.connection:
            self.connection.commit()
            self.connection.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
