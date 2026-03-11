from __future__ import annotations

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
