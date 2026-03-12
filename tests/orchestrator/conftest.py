"""Orchestrator 测试模块的共享 fixtures。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, JobDetail
from minutes_inference.service import InferenceService
from minutes_orchestrator.services import OrchestratorService
from tests.helpers import RecordingEventBus, RecordingQueue


@dataclass(slots=True)
class ServiceEnv:
    """Orchestrator/Inference 测试的共享基础设施。"""

    settings: Settings
    session_factory: sessionmaker
    queue: RecordingQueue
    events: RecordingEventBus
    tmp_path: Path
    media_path: Path

    def make_orchestrator(self) -> OrchestratorService:
        """创建使用当前测试环境的 OrchestratorService。"""
        return OrchestratorService(
            settings=self.settings,
            session_factory=self.session_factory,
            event_bus=self.events,
            queue_dispatcher=self.queue,
        )

    def make_inference(self) -> InferenceService:
        """创建使用当前测试环境的 InferenceService。"""
        return InferenceService(
            settings=self.settings,
            session_factory=self.session_factory,
            event_bus=self.events,
            queue_dispatcher=self.queue,
        )

    def get_job(self, job_id: str) -> JobDetail | None:
        """便捷方法：从数据库获取 job 详情。"""
        with self.session_factory() as session:
            return JobRepository(session).get_job(job_id)


@pytest.fixture
def service_env(tmp_path) -> ServiceEnv:
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

    return ServiceEnv(
        settings=settings,
        session_factory=session_factory,
        queue=queue,
        events=events,
        tmp_path=tmp_path,
        media_path=media_path,
    )


def create_test_job(
    env: ServiceEnv,
    *,
    sync_mode: bool = False,
    job_id: str | None = None,
    media_path: Path | None = None,
) -> str:
    """在数据库中创建一个测试用的 job 并返回其 ID。"""
    jid = job_id or str(uuid.uuid4())
    source = media_path or env.media_path
    output_dir = env.tmp_path / "artifacts" / jid
    output_dir.mkdir(parents=True, exist_ok=True)
    with env.session_factory() as session:
        detail = JobRepository(session).create_job(
            JobCreate(
                job_id=jid,
                source_filename=source.name,
                source_content_type="audio/wav",
                source_path=str(source),
                output_dir=str(output_dir),
                profile=JobProfile.CN_MEETING,
                language="zh",
                sync_mode=sync_mode,
            )
        )
        session.commit()
        return detail.id
