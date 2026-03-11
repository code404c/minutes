from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class PoolEntry[T]:
    value: T
    last_used: float


class TTLModelPool[T]:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, PoolEntry[T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self.ttl_seconds >= 0 and time.monotonic() - entry.last_used > self.ttl_seconds:
                self._entries.pop(key, None)
                return None
            entry.last_used = time.monotonic()
            return entry.value

    def put(self, key: str, value: T) -> T:
        with self._lock:
            self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
            return value

    def get_or_create(self, key: str, loader: Callable[[], T]) -> T:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and not self._is_expired(entry):
                entry.last_used = time.monotonic()
                return entry.value

            if entry is not None:
                self._entries.pop(key, None)

            value = loader()
            self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
            return value

    def _is_expired(self, entry: PoolEntry[T]) -> bool:
        return self.ttl_seconds >= 0 and time.monotonic() - entry.last_used > self.ttl_seconds
