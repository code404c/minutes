"""Inference 测试模块的共享 fixtures。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from minutes_core.config import Settings
from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile
from minutes_core.schemas import JobDetail
from tests.orchestrator.conftest import service_env as service_env  # noqa: F401 — re-export fixture


@pytest.fixture
def inference_settings(tmp_path: Path) -> Settings:
    """提供带有 model_cache_dir 的 Settings 用于引擎测试。"""
    return Settings(
        database_url="sqlite://",
        storage_root=tmp_path,
        redis_url="redis://unused:6379/0",
        fake_inference=False,
        model_cache_dir=tmp_path / "model_cache",
        inference_device="cpu",
    )


def make_job_detail(
    *,
    job_id: str = "test-job",
    profile: JobProfile = JobProfile.CN_MEETING,
    language: str | None = "zh",
    hotwords: list[str] | None = None,
    duration_ms: int | None = 5_000,
) -> JobDetail:
    """构建测试用的 JobDetail 实例。"""
    now = datetime.now(tz=UTC)
    return JobDetail(
        id=job_id,
        status=JobStatus.TRANSCRIBING,
        profile=profile,
        source_filename="meeting.wav",
        source_content_type="audio/wav",
        source_path="/tmp/meeting.wav",
        output_dir="/tmp/artifacts",
        duration_ms=duration_ms,
        language=language,
        hotwords=hotwords or [],
        progress=50,
        created_at=now,
        updated_at=now,
    )
