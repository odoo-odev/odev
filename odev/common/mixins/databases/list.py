from abc import ABC
from typing import Callable, List

from odev.common.mixins import PostgresConnectorMixin


class ListLocalDatabasesMixin(PostgresConnectorMixin, ABC):
    """Mixin to list local databases."""

    def list_databases(self, predicate: Callable[[str], bool] = None) -> List[str]:
        """List the names of all local databases, excluding templates
        and the default 'postgres' database.
        :param predicate: a function that takes a database name as argument and returns
            True if the database should be included in the list.
        """
        with self.psql() as psql:
            databases = psql.query(
                """
                SELECT datname
                FROM pg_database
                WHERE datistemplate = false
                ORDER by datname
                """
            )

        if predicate is None:

            def default_predicate(_: str) -> bool:
                return True

            predicate = default_predicate

        return [database[0] for database in databases if predicate(database[0])]
