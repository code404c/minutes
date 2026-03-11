from __future__ import annotations

from pathlib import Path
import uuid

from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory, init_database
from minutes_core.media import MediaProbe, MediaProcessingError
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate
from minutes_inference.service import InferenceService
from minutes_orchestrator.services import OrchestratorService


class RecordingQueue:
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
    def __init__(self) -> None:
        self.events: list[tuple[str, str, int]] = []

    def publish(self, event) -> None:
        self.events.append((event.stage, event.status.value, event.progress))


def _create_job(session_factory, storage_root: Path, media_path: Path) -> str:
    job_id = str(uuid.uuid4())
    output_dir = storage_root / "artifacts" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    with session_factory() as session:
        detail = JobRepository(session).create_job(
            JobCreate(
                job_id=job_id,
                source_filename=media_path.name,
                source_content_type="audio/wav",
                source_path=str(media_path),
                output_dir=str(output_dir),
                profile=JobProfile.CN_MEETING,
                language="zh",
            )
        )
        return detail.id


def test_prepare_job_normalizes_media_and_dispatches_transcription(tmp_path, monkeypatch) -> None:
    media_path = tmp_path / "input.wav"
    media_path.write_bytes(b"fake-audio")

    from minutes_core.config import Settings

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
    job_id = _create_job(session_factory, tmp_path, media_path)

    def fake_probe(_path: Path) -> MediaProbe:
        return MediaProbe(duration_ms=4_000, format_name="wav")

    def fake_transcode(_source: Path, output: Path) -> Path:
        output.write_bytes(b"normalized")
        return output

    monkeypatch.setattr("minutes_orchestrator.services.probe_media", fake_probe)
    monkeypatch.setattr("minutes_orchestrator.services.transcode_to_wav", fake_transcode)

    service = OrchestratorService(
        settings=settings,
        session_factory=session_factory,
        event_bus=events,
        queue_dispatcher=queue,
    )
    service.prepare_job(job_id)

    with session_factory() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.PREPROCESSING
    assert detail.duration_ms == 4_000
    assert detail.normalized_path is not None
    assert Path(detail.normalized_path).exists()
    assert queue.transcribed == [job_id]
    assert ("prepare", "preprocessing", 25) in events.events


def test_end_to_end_pipeline_completes_with_fake_inference(tmp_path, monkeypatch) -> None:
    media_path = tmp_path / "input.wav"
    media_path.write_bytes(b"fake-audio")

    from minutes_core.config import Settings

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
    job_id = _create_job(session_factory, tmp_path, media_path)

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _path: MediaProbe(duration_ms=3_000, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _source, output: output.write_bytes(b"normalized") or output,
    )

    orchestrator = OrchestratorService(
        settings=settings,
        session_factory=session_factory,
        event_bus=events,
        queue_dispatcher=queue,
    )
    inference = InferenceService(
        settings=settings,
        session_factory=session_factory,
        event_bus=events,
        queue_dispatcher=queue,
    )

    orchestrator.prepare_job(job_id)
    inference.transcribe_job(job_id)
    orchestrator.finalize_job(job_id)

    with session_factory() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.COMPLETED
    assert detail.result is not None
    assert "Fake transcript" in detail.result.full_text
    assert queue.transcribed == [job_id]
    assert queue.finalized == [job_id]
    assert ("finalize", "completed", 100) in events.events


def test_prepare_job_marks_failure_when_media_processing_errors(tmp_path, monkeypatch) -> None:
    media_path = tmp_path / "broken.m4a"
    media_path.write_bytes(b"broken")

    from minutes_core.config import Settings

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
    job_id = _create_job(session_factory, tmp_path, media_path)

    def explode(_path: Path) -> MediaProbe:
        raise MediaProcessingError("ffprobe failed")

    monkeypatch.setattr("minutes_orchestrator.services.probe_media", explode)

    service = OrchestratorService(
        settings=settings,
        session_factory=session_factory,
        event_bus=events,
        queue_dispatcher=queue,
    )
    service.prepare_job(job_id)

    with session_factory() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "MEDIA_PROCESSING_FAILED"
    assert queue.transcribed == []
    assert ("prepare", "failed", 0) in events.events

