"""Caching implementations for various purposes."""

from datetime import datetime
from typing import Any


class TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self.cache = {}

    def get(self, key: str) -> Any | None:
        if key not in self.cache:
            return None

        if (datetime.now() - self.cache[key]["timestamp"]).total_seconds() > self.ttl:
            del self.cache[key]
            return None

        return self.cache[key]["value"]

    def set(self, key: str, value: Any) -> None:
        self.cache[key] = {"value": value, "timestamp": datetime.now()}

    def __contains__(self, key: str) -> bool:
        return key in self.cache

    def __len__(self) -> int:
        return len(self.cache)

    def __repr__(self) -> str:
        return f"TTLCache(ttl={self.ttl}, cached={len(self.cache)})"
