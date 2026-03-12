from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class PoolEntry[T]:
    """
    模型池条目。

    用于存储实际的模型对象以及它最后一次被使用的时间戳。
    """

    value: T
    last_used: float


class TTLModelPool[T]:
    """
    具有生存时间 (TTL) 限制的模型池。

    该类用于管理昂贵的资源（如机器学习模型），在一段时间不使用后会自动释放它们，
    以节省内存或 GPU 显存。
    """

    def __init__(self, ttl_seconds: int) -> None:
        """
        初始化模型池。

        Args:
            ttl_seconds: 生存时间（秒）。如果小于 0，则模型永不过期。
        """
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, PoolEntry[T]] = {}
        self._lock = threading.Lock()  # 用于保证线程安全的锁

    def get(self, key: str) -> T | None:
        """
        根据键获取模型。如果模型不存在或已过期，则返回 None。
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._is_expired(entry):
                self._entries.pop(key, None)
                return None
            # 更新最后使用时间
            entry.last_used = time.monotonic()
            return entry.value

    def put(self, key: str, value: T) -> T:
        """
        将模型放入池中。
        """
        with self._lock:
            self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
            return value

    def get_or_create(self, key: str, loader: Callable[[], T]) -> T:
        """
        获取模型，如果不存在或已过期，则使用提供的加载器创建新模型。

        这是一个原子操作，确保在高并发环境下模型加载的一致性。
        """
        with self._lock:
            entry = self._entries.get(key)
            # 检查是否存在且未过期
            if entry is not None and not self._is_expired(entry):
                entry.last_used = time.monotonic()
                return entry.value

            # 如果已过期，先移除
            if entry is not None:
                self._entries.pop(key, None)

            # 调用加载器加载模型
            value = loader()
            self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
            return value

    def _is_expired(self, entry: PoolEntry[T]) -> bool:
        """
        检查条目是否已过期。
        """
        return self.ttl_seconds >= 0 and time.monotonic() - entry.last_used > self.ttl_seconds
