from __future__ import annotations

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate


def test_repository_create_job_does_not_commit_implicitly(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'tx.db'}",
        storage_root=tmp_path / "storage",
        redis_url="redis://unused:6379/0",
    )
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])

    payload = JobCreate(
        job_id="job-123",
        source_filename="meeting.wav",
        source_content_type="audio/wav",
        source_path=str(tmp_path / "meeting.wav"),
        output_dir=str(tmp_path / "artifacts"),
        profile=JobProfile.CN_MEETING,
        language="zh",
        hotwords=["预算"],
    )

    with session_factory() as writer, session_factory() as reader:
        repo = JobRepository(writer)
        repo.create_job(payload)

        assert JobRepository(reader).get_job(payload.job_id) is None

        writer.commit()
        reader.expire_all()

        persisted = JobRepository(reader).get_job(payload.job_id)

    assert persisted is not None
    assert persisted.id == payload.job_id
