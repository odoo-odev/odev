from collections.abc import Sequence
from datetime import date, datetime
from typing import (
    Literal,
)


RecordData = dict[str, str | int | float | bool | tuple[int, str] | list[int]]
"""Type alias for a record data dictionary as returned from the Odoo RPC API."""

RecordDataList = list[RecordData]
"""Type alias for a list of record data dictionaries as returned from the Odoo RPC API,
notably the raw result of calls to `search_read`.
"""

Domain = list[
    Literal["&", "|", "!"]
    | tuple[
        str,
        Literal["=", "!=", ">", ">=", "<", "<=", "like", "ilike", "=like", "=ilike", "in", "not in", "any", "not any"],
        str | int | float | bool | date | datetime | Sequence[str] | Sequence[int],
    ]
]
"""Type alias for a domain as used in Odoo RPC calls."""
