from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, Segment, TranscriptDocument


@pytest.fixture
def source_audio_path(tmp_path: Path) -> Path:
    path = tmp_path / "meeting.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    return path


@pytest.fixture
def sqlite_database_path(tmp_path: Path) -> Path:
    return tmp_path / "core-tests.db"


@pytest.fixture
def sqlite_session(sqlite_database_path: Path, tmp_path: Path) -> Iterator[Session]:
    settings = Settings(
        database_url=f"sqlite:///{sqlite_database_path}",
        storage_root=tmp_path / "storage",
    )
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])

    with session_factory() as session:
        yield session


@pytest.fixture
def job_repository(sqlite_session: Session) -> JobRepository:
    return JobRepository(sqlite_session)


@pytest.fixture
def job_create_payload(source_audio_path: Path, tmp_path: Path) -> JobCreate:
    output_dir = tmp_path / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return JobCreate(
        source_filename=source_audio_path.name,
        source_content_type="audio/wav",
        source_path=str(source_audio_path),
        output_dir=str(output_dir),
        profile=JobProfile.CN_MEETING,
        language="zh",
        hotwords=["OpenAI", "会议纪要"],
        sync_mode=True,
    )


@pytest.fixture
def sample_transcript_document() -> TranscriptDocument:
    return TranscriptDocument(
        job_id="job-123",
        language="zh",
        full_text="你好，世界\n这是第二句。",
        segments=[
            Segment(
                start_ms=0,
                end_ms=1500,
                speaker_id="spk-1",
                text="你好，世界",
                confidence=0.98,
            ),
            Segment(
                start_ms=1500,
                end_ms=3200,
                speaker_id="spk-1",
                text="这是第二句。",
                confidence=0.97,
            ),
        ],
        paragraphs=["你好，世界", "这是第二句。"],
        speakers=[],
        model_profile=JobProfile.CN_MEETING,
    )
