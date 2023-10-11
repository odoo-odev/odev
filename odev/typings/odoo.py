from datetime import date, datetime
from typing import (
    List,
    Literal,
    Mapping,
    Tuple,
    Union,
)


RecordData = Mapping[str, Union[str, int, bool]]
"""Type alias for a record data dictionary as returned from the Odoo RPC API."""

RecordDataList = Mapping[int, RecordData]
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
            ],
        ],
    ]
]
"""Type alias for a domain as used in Odoo RPC calls."""
