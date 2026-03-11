from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from minutes_core.constants import JobStatus
from minutes_core.models import JobRecord
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, TranscriptDocument


def test_job_repository_create_job_persists_sqlite_record(
    job_repository: JobRepository,
    sqlite_session: Session,
    sqlite_database_path: Path,
    job_create_payload: JobCreate,
) -> None:
    detail = job_repository.create_job(job_create_payload)
    record = sqlite_session.get(JobRecord, detail.id)

    assert detail.status is JobStatus.QUEUED
    assert detail.profile is JobProfile.CN_MEETING
    assert detail.progress == 0
    assert detail.sync_mode is True
    assert sqlite_database_path.exists()
    assert record is not None
    assert record.source_filename == "meeting.wav"
    assert record.source_content_type == "audio/wav"
    assert record.source_path == job_create_payload.source_path
    assert record.output_dir == job_create_payload.output_dir
    assert json.loads(record.hotwords_json) == ["OpenAI", "会议纪要"]


def test_job_repository_update_job_updates_status_and_metadata(
    job_repository: JobRepository,
    sqlite_session: Session,
    job_create_payload: JobCreate,
) -> None:
    created = job_repository.create_job(job_create_payload)

    updated = job_repository.update_job(
        created.id,
        status=JobStatus.COMPLETED,
        progress=100,
        normalized_path="/tmp/normalized.wav",
        duration_ms=3200,
        language="zh",
    )
    record = sqlite_session.get(JobRecord, created.id)

    assert updated.status is JobStatus.COMPLETED
    assert updated.progress == 100
    assert updated.normalized_path == "/tmp/normalized.wav"
    assert updated.duration_ms == 3200
    assert updated.language == "zh"
    assert updated.completed_at is not None
    assert record is not None
    assert record.status == JobStatus.COMPLETED.value
    assert record.progress == 100
    assert record.normalized_path == "/tmp/normalized.wav"
    assert record.completed_at is not None


def test_job_repository_save_result_persists_transcript_document(
    job_repository: JobRepository,
    sqlite_session: Session,
    job_create_payload: JobCreate,
    sample_transcript_document: TranscriptDocument,
) -> None:
    created = job_repository.create_job(job_create_payload)
    document = sample_transcript_document.model_copy(update={"job_id": created.id})

    saved = job_repository.save_result(created.id, document)
    fetched = job_repository.get_job(created.id)
    record = sqlite_session.get(JobRecord, created.id)

    assert saved.status is JobStatus.COMPLETED
    assert saved.progress == 100
    assert saved.result is not None
    assert saved.result.model_dump() == document.model_dump()
    assert fetched is not None
    assert fetched.result is not None
    assert fetched.result.full_text == "你好，世界\n这是第二句。"
    assert fetched.result.segments[0].text == "你好，世界"
    assert record is not None
    assert json.loads(record.result_json)["job_id"] == created.id
    assert json.loads(record.result_json)["segments"][1]["text"] == "这是第二句。"
