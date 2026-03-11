from __future__ import annotations

from minutes_core.config import Settings
from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate
from minutes_inference.service import InferenceService


class RecordingQueue:
    def enqueue_prepare_job(self, _job_id: str) -> None:
        return None

    def enqueue_transcription_job(self, _job_id: str) -> None:
        return None

    def enqueue_finalize_job(self, _job_id: str) -> None:
        return None


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def publish(self, event) -> None:
        self.events.append((event.status.value, event.stage))


def test_mark_retry_exhausted_marks_inference_job_failed(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        storage_root=tmp_path,
        redis_url="redis://unused:6379/0",
        fake_inference=True,
    )
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])

    with session_factory() as session:
        repo = JobRepository(session)
        created = repo.create_job(
            JobCreate(
                job_id="job-123",
                source_filename="meeting.wav",
                source_content_type="audio/wav",
                source_path=str(tmp_path / "meeting.wav"),
                output_dir=str(tmp_path / "artifacts"),
                profile=JobProfile.CN_MEETING,
                language="zh",
            )
        )
        repo.update_job(created.id, status=JobStatus.TRANSCRIBING, progress=50)
        session.commit()

    event_bus = RecordingEventBus()
    service = InferenceService(
        settings=settings,
        session_factory=session_factory,
        event_bus=event_bus,
        queue_dispatcher=RecordingQueue(),
    )

    service.mark_retry_exhausted("job-123", retries=2, max_retries=2)

    with session_factory() as session:
        detail = JobRepository(session).get_job("job-123")

    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "INFERENCE_RETRY_EXHAUSTED"
    assert ("failed", "transcribe") in event_bus.events
