from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.events import EventBus
from minutes_core.schemas import JobEvent
from minutes_gateway.app import create_app


class FakeQueueDispatcher:
    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.transcribed: list[str] = []
        self.finalized: list[str] = []

    def enqueue_prepare_job(self, job_id: str) -> None:
        self.prepared.append(job_id)

    def enqueue_finalize_job(self, job_id: str) -> None:
        self.finalized.append(job_id)

    def enqueue_transcription_job(self, job_id: str) -> None:
        self.transcribed.append(job_id)


class FakeEventBus(EventBus):
    def __init__(self) -> None:
        self.messages: dict[str, list[str]] = defaultdict(list)

    def publish(self, event: JobEvent) -> None:
        self.messages[event.job_id].append(event.model_dump_json())

    async def subscribe(self, job_id: str) -> AsyncIterator[str]:
        for message in self.messages[job_id]:
            yield message


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        service_name="test",
        log_json=False,
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        redis_url="redis://unused:6379/0",
        storage_root=tmp_path / "data",
        fake_inference=True,
        sync_wait_timeout_s=1,
    )


@pytest.fixture
def session_factory(test_settings: Settings):
    factory = create_session_factory(test_settings)
    init_database(factory.kw["bind"])
    return factory


@pytest.fixture
def fake_queue_dispatcher() -> FakeQueueDispatcher:
    return FakeQueueDispatcher()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def app(
    test_settings: Settings, session_factory, fake_queue_dispatcher: FakeQueueDispatcher, fake_event_bus: FakeEventBus
):
    return create_app(
        settings=test_settings,
        session_factory=session_factory,
        queue_dispatcher=fake_queue_dispatcher,
        event_bus=fake_event_bus,
    )
