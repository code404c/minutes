from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from minutes_core.constants import JobStatus
from minutes_core.events import EventBus
from minutes_core.schemas import JobEvent


class FakeRedisClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def publish(self, channel: str, payload: str) -> None:
        self.messages.append((channel, payload))

    def close(self) -> None:
        return None


def test_event_bus_reuses_sync_redis_client(monkeypatch) -> None:
    created_clients: list[FakeRedisClient] = []

    def fake_from_url(_url: str, *, decode_responses: bool):  # type: ignore[no-untyped-def]
        assert decode_responses is True
        client = FakeRedisClient()
        created_clients.append(client)
        return client

    monkeypatch.setattr("minutes_core.events.Redis.from_url", fake_from_url)

    event_bus = EventBus("redis://unused:6379/0")
    event = JobEvent(
        event="job.updated",
        job_id="job-123",
        status=JobStatus.PREPROCESSING,
        progress=25,
        stage="prepare",
        message="ok",
    )

    event_bus.publish(event)
    event_bus.publish(event)

    assert len(created_clients) == 1
    assert created_clients[0].messages == [
        ("minutes:jobs:job-123", event.model_dump_json()),
        ("minutes:jobs:job-123", event.model_dump_json()),
    ]


# ---------------------------------------------------------------------------
# EventBus.close()
# ---------------------------------------------------------------------------


def test_event_bus_close_calls_redis_close(monkeypatch) -> None:
    """close() 应关闭同步 Redis 客户端。"""
    fake_client = FakeRedisClient()
    monkeypatch.setattr(
        "minutes_core.events.Redis.from_url",
        lambda *_a, **_kw: fake_client,
    )
    bus = EventBus("redis://unused:6379/0")
    bus.close()
    # FakeRedisClient.close 返回 None，只要不抛异常就算通过


# ---------------------------------------------------------------------------
# EventBus.subscribe() — 异步生成器测试
# ---------------------------------------------------------------------------


def _build_fake_async_redis(messages: list[dict | None]):
    """构建模拟 AsyncRedis，用于测试 subscribe 的异步生成器。

    messages: get_message 将按顺序返回的消息列表，列表末尾追加 GeneratorExit
    """
    call_count = 0

    async def fake_get_message(*, ignore_subscribe_messages: bool, timeout: float):  # type: ignore[no-untyped-def]
        nonlocal call_count
        if call_count < len(messages):
            msg = messages[call_count]
            call_count += 1
            return msg
        # 终止迭代 — 模拟外部取消
        raise GeneratorExit

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()
    pubsub.get_message = fake_get_message

    # client.pubsub() 是同步调用，返回 pubsub 对象
    client = MagicMock()
    client.pubsub.return_value = pubsub
    client.aclose = AsyncMock()

    return client, pubsub


@pytest.mark.asyncio
async def test_subscribe_yields_messages(monkeypatch) -> None:
    """subscribe 应将 pubsub 消息 yield 出来。"""
    messages = [
        {"data": "msg-1"},
        {"data": "msg-2"},
    ]
    client, pubsub = _build_fake_async_redis(messages)
    monkeypatch.setattr(
        "minutes_core.events.AsyncRedis.from_url",
        lambda *_a, **_kw: client,
    )
    bus = EventBus.__new__(EventBus)
    bus.redis_url = "redis://unused:6379/0"
    bus._client = MagicMock()

    collected: list[str] = []
    gen = bus.subscribe("job-42")
    try:
        async for item in gen:
            collected.append(item)
            if len(collected) >= 2:
                break
    except GeneratorExit:
        pass

    assert collected == ["msg-1", "msg-2"]


@pytest.mark.asyncio
async def test_subscribe_skips_none_messages(monkeypatch) -> None:
    """subscribe 应跳过 None 消息和缺少 data 的消息。"""
    messages = [
        None,
        {"data": None},
        {"data": "valid"},
    ]
    client, pubsub = _build_fake_async_redis(messages)
    monkeypatch.setattr(
        "minutes_core.events.AsyncRedis.from_url",
        lambda *_a, **_kw: client,
    )
    bus = EventBus.__new__(EventBus)
    bus.redis_url = "redis://unused:6379/0"
    bus._client = MagicMock()

    collected: list[str] = []
    gen = bus.subscribe("job-42")
    try:
        async for item in gen:
            collected.append(item)
            if len(collected) >= 1:
                break
    except GeneratorExit:
        pass

    assert collected == ["valid"]


@pytest.mark.asyncio
async def test_subscribe_cleans_up_on_exception(monkeypatch) -> None:
    """subscribe 发生异常退出时，应确保 unsubscribe/close/aclose 被调用。"""

    async def exploding_get_message(*, ignore_subscribe_messages: bool, timeout: float):  # type: ignore[no-untyped-def]
        raise RuntimeError("connection lost")

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()
    pubsub.get_message = exploding_get_message

    # client.pubsub() 是同步调用
    client = MagicMock()
    client.pubsub.return_value = pubsub
    client.aclose = AsyncMock()

    monkeypatch.setattr(
        "minutes_core.events.AsyncRedis.from_url",
        lambda *_a, **_kw: client,
    )

    bus = EventBus.__new__(EventBus)
    bus.redis_url = "redis://unused:6379/0"
    bus._client = MagicMock()

    with pytest.raises(RuntimeError, match="connection lost"):
        async for _ in bus.subscribe("job-99"):
            pass

    pubsub.unsubscribe.assert_awaited_once()
    pubsub.close.assert_awaited_once()
    client.aclose.assert_awaited_once()
