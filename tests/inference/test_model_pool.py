from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from minutes_inference.model_pool import TTLModelPool


def test_ttl_model_pool_get_or_create_loads_once_under_concurrency() -> None:
    pool: TTLModelPool[str] = TTLModelPool(ttl_seconds=60)
    calls: list[int] = []
    call_lock = Lock()

    def loader() -> str:
        with call_lock:
            calls.append(1)
        return "model"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: pool.get_or_create("cn_meeting", loader), range(16)))

    assert results == ["model"] * 16
    assert len(calls) == 1
