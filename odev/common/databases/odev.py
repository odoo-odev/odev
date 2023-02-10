from abc import ABC
from typing import Mapping

from odev.common.databases import PostgresDatabase
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class OdevDatabase(PostgresDatabase, ABC):
    """Specific class for the odev database."""

    name = "odev"
    """Name of the database."""

    _table: str
    """Name of the table in which data is stored, must be set in subclass."""

    _columns: Mapping[str, str]
    """Columns definition of the table, must be set in subclass.
    Format: `{column_name: column_type}` where `column_type` is the SQL definition of the column.
    """

    def __init__(self):
        """Initialize the database."""
        super().__init__(self.name)
        self._prepare_database()

    def _prepare_database(self):
        """Prepare the database and ensure it exists and has the required tables."""
        with self:
            if not self.exists():
                logger.debug(f"Creating database {self.name!r}")
                self.create()

            if not self.table_exists(self._table):
                logger.debug(f"Creating table {self._table!r} in database {self!r}")
                self.create_table(self._table, self._columns)
