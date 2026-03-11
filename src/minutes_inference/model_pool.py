from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class PoolEntry(Generic[T]):
    value: T
    last_used: float


class TTLModelPool(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, PoolEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self.ttl_seconds >= 0 and time.monotonic() - entry.last_used > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        entry.last_used = time.monotonic()
        return entry.value

    def put(self, key: str, value: T) -> T:
        self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
        return value

