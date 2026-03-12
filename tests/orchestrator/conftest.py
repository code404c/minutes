"""Orchestrator 测试模块的共享 fixtures。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate


class RecordingQueue:
    """记录所有入队调用的 Fake 队列分发器。"""

    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.transcribed: list[str] = []
        self.finalized: list[str] = []

    def enqueue_prepare_job(self, job_id: str) -> None:
        self.prepared.append(job_id)

    def enqueue_transcription_job(self, job_id: str) -> None:
        self.transcribed.append(job_id)

    def enqueue_finalize_job(self, job_id: str) -> None:
        self.finalized.append(job_id)


class RecordingEventBus:
    """记录所有发布事件的 Fake 事件总线。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, int]] = []

    def publish(self, event) -> None:  # type: ignore[no-untyped-def]
        self.events.append((event.stage, event.status.value, event.progress))


@pytest.fixture
def service_env(tmp_path):
    """创建 Orchestrator/Inference 测试所需的基础设施。"""
    media_path = tmp_path / "input.wav"
    media_path.write_bytes(b"fake-audio")

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        storage_root=tmp_path,
        redis_url="redis://unused:6379/0",
        fake_inference=True,
    )
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])
    queue = RecordingQueue()
    events = RecordingEventBus()

    return {
        "settings": settings,
        "session_factory": session_factory,
        "queue": queue,
        "events": events,
        "tmp_path": tmp_path,
        "media_path": media_path,
    }


def create_test_job(
    session_factory,
    tmp_path: Path,
    media_path: Path,
    *,
    sync_mode: bool = False,
    job_id: str | None = None,
) -> str:
    """在数据库中创建一个测试用的 job 并返回其 ID。"""
    jid = job_id or str(uuid.uuid4())
    output_dir = tmp_path / "artifacts" / jid
    output_dir.mkdir(parents=True, exist_ok=True)
    with session_factory() as session:
        detail = JobRepository(session).create_job(
            JobCreate(
                job_id=jid,
                source_filename=media_path.name,
                source_content_type="audio/wav",
                source_path=str(media_path),
                output_dir=str(output_dir),
                profile=JobProfile.CN_MEETING,
                language="zh",
                sync_mode=sync_mode,
            )
        )
        session.commit()
        return detail.id
