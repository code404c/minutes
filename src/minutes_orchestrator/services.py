from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings
from minutes_core.constants import JobStatus, SYNC_TRANSCRIPTION_MAX_DURATION_MS
from minutes_core.db import create_session_factory
from minutes_core.events import EventBus
from minutes_core.media import MediaProcessingError, probe_media, transcode_to_wav
from minutes_core.queue import DramatiqQueueDispatcher, QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobEvent, TranscriptDocument


class OrchestratorService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker | None = None,
        event_bus: EventBus | None = None,
        queue_dispatcher: QueueDispatcher | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory or create_session_factory(settings)
        self.event_bus = event_bus or EventBus(settings.redis_url)
        self.queue_dispatcher = queue_dispatcher or DramatiqQueueDispatcher()

    def prepare_job(self, job_id: str) -> None:
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                raise KeyError(job_id)
            repository.update_job(job_id, status=JobStatus.PREPROCESSING, progress=5)
            self._publish(job_id, JobStatus.PREPROCESSING, 5, "prepare", "Job accepted for preprocessing.")

            try:
                probe = probe_media(Path(detail.source_path))
                if detail.sync_mode and probe.duration_ms > SYNC_TRANSCRIPTION_MAX_DURATION_MS:
                    repository.update_job(
                        job_id,
                        status=JobStatus.FAILED,
                        progress=0,
                        error_code="SYNC_DURATION_LIMIT_EXCEEDED",
                        error_message="Synchronous OpenAI-compatible transcription only supports media up to 15 minutes.",
                    )
                    self._publish(job_id, JobStatus.FAILED, 0, "prepare", "Synchronous duration limit exceeded.")
                    return

                normalized_path = Path(detail.output_dir) / "normalized.wav"
                transcode_to_wav(Path(detail.source_path), normalized_path)
                repository.update_job(
                    job_id,
                    status=JobStatus.PREPROCESSING,
                    progress=25,
                    normalized_path=str(normalized_path),
                    duration_ms=probe.duration_ms,
                    language=detail.language or "auto",
                )
                self._publish(job_id, JobStatus.PREPROCESSING, 25, "prepare", "Media normalized to 16k mono WAV.")
            except MediaProcessingError as exc:
                repository.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    progress=0,
                    error_code="MEDIA_PROCESSING_FAILED",
                    error_message=str(exc),
                )
                self._publish(job_id, JobStatus.FAILED, 0, "prepare", str(exc))
                return

        self.queue_dispatcher.enqueue_transcription_job(job_id)

    def finalize_job(self, job_id: str) -> None:
        raw_path = self.settings.artifacts_dir / job_id / "raw_transcript.json"
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                raise KeyError(job_id)
            try:
                repository.update_job(job_id, status=JobStatus.POSTPROCESSING, progress=90)
                self._publish(job_id, JobStatus.POSTPROCESSING, 90, "finalize", "Aggregating transcript.")
                document = TranscriptDocument.model_validate_json(raw_path.read_text(encoding="utf-8"))
                repository.save_result(job_id, document)
                self._publish(job_id, JobStatus.COMPLETED, 100, "finalize", "Transcript completed.")
            except Exception as exc:
                repository.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    progress=90,
                    error_code="FINALIZE_FAILED",
                    error_message=str(exc),
                )
                self._publish(job_id, JobStatus.FAILED, 90, "finalize", str(exc))

    def _publish(self, job_id: str, status: JobStatus, progress: int, stage: str, message: str) -> None:
        self.event_bus.publish(
            JobEvent(
                event="job.updated",
                job_id=job_id,
                status=status,
                progress=progress,
                stage=stage,
                message=message,
            )
        )
