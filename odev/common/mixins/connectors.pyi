from typing import Type

from odev.common.mixins.connectors import *
from odev.common.connectors import *

class PostgresConnectorMixin:
    """Mixin for commands that need to use a PostgreSQL connector.
    Provides a `PostgresConnector` connector in `self.psql`.

    >>> with self.psql(...) as psql:
    >>>     ...
    """

    psql: Type[PostgresConnector]
