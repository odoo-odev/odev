from datetime import date, datetime
from typing import (
    Dict,
    List,
    Literal,
    Sequence,
    Tuple,
    Union,
)


RecordData = Dict[str, Union[str, int, float, bool, Tuple[int, str], List[int]]]
"""Type alias for a record data dictionary as returned from the Odoo RPC API."""

RecordDataList = List[RecordData]
"""Type alias for a list of record data dictionaries as returned from the Odoo RPC API,
notably the raw result of calls to `search_read`.
"""

Domain = List[
    Union[
        Literal["&", "|", "!"],
        Tuple[
            str,
            Literal[
                "=",
                "!=",
                ">",
                ">=",
                "<",
                "<=",
                "like",
                "ilike",
                "=like",
                "=ilike",
                "in",
                "not in",
                "any",
                "not any",
            ],
            Union[
                str,
                int,
                float,
                bool,
                date,
                datetime,
                Sequence[str],
                Sequence[int],
            ],
        ],
    ]
]
"""Type alias for a domain as used in Odoo RPC calls."""
