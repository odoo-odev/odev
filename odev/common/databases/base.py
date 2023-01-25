"""Handling of database information."""

from abc import ABC
from typing import Any, MutableMapping


class Database(ABC):
    """Base abstract class for manipulating databases."""

    name: str = None
    """The name of the database."""

    def __init__(self, name: str):
        """Initialize the database."""
        self.name = name

    def info(self) -> MutableMapping[str, Any]:
        """Return information about the database."""
        return {"name": self.name}
