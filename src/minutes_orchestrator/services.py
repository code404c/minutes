from __future__ import annotations

from pathlib import Path

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings
from minutes_core.constants import SYNC_TRANSCRIPTION_MAX_DURATION_MS, JobStatus
from minutes_core.db import create_session_factory
from minutes_core.events import EventBus
from minutes_core.media import MediaProcessingError, probe_media, transcode_to_wav
from minutes_core.queue import DramatiqQueueDispatcher, QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobEvent, TranscriptDocument

_PREPARE_NOOP_STATUSES = {
    JobStatus.TRANSCRIBING,
    JobStatus.POSTPROCESSING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
}
_FINALIZE_NOOP_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.PREPROCESSING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
}


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
                logger.warning("Prepare job {} no longer exists.", job_id)
                return
            if detail.status in _PREPARE_NOOP_STATUSES:
                logger.info("Skipping prepare for job {} in status {}.", job_id, detail.status.value)
                return
            if detail.status == JobStatus.PREPROCESSING and detail.normalized_path:
                normalized_path = Path(detail.normalized_path)
                if normalized_path.exists():
                    self.queue_dispatcher.enqueue_transcription_job(job_id)
                    return

            try:
                self._set_progress(repository, session, job_id, progress=5)
                probe = probe_media(Path(detail.source_path))
                if detail.sync_mode and probe.duration_ms > SYNC_TRANSCRIPTION_MAX_DURATION_MS:
                    self._mark_failed(
                        repository,
                        session,
                        job_id,
                        error_code="SYNC_DURATION_LIMIT_EXCEEDED",
                        message="Synchronous OpenAI-compatible transcription only supports media up to 15 minutes.",
                        progress=0,
                        stage="prepare",
                    )
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
                session.commit()
                self._publish(job_id, JobStatus.PREPROCESSING, 25, "prepare", "Media normalized to 16k mono WAV.")
            except MediaProcessingError as exc:
                session.rollback()
                self._mark_failed(
                    repository,
                    session,
                    job_id,
                    error_code="MEDIA_PROCESSING_FAILED",
                    message=str(exc),
                    progress=0,
                    stage="prepare",
                )
                return
            except Exception:
                session.rollback()
                raise

        self.queue_dispatcher.enqueue_transcription_job(job_id)

    def finalize_job(self, job_id: str) -> None:
        raw_path = self.settings.artifacts_dir / job_id / "raw_transcript.json"
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                logger.warning("Finalize job {} no longer exists.", job_id)
                return
            if detail.status in _FINALIZE_NOOP_STATUSES:
                logger.info("Skipping finalize for job {} in status {}.", job_id, detail.status.value)
                return
            if detail.result is not None:
                logger.info("Skipping finalize for job {} because result already exists.", job_id)
                return
            if not raw_path.exists():
                self._mark_failed(
                    repository,
                    session,
                    job_id,
                    error_code="FINALIZE_INPUT_MISSING",
                    message="Raw transcript artifact is missing.",
                    progress=90,
                    stage="finalize",
                )
                return
            try:
                repository.update_job(job_id, status=JobStatus.POSTPROCESSING, progress=90)
                session.commit()
                self._publish(job_id, JobStatus.POSTPROCESSING, 90, "finalize", "Aggregating transcript.")
                document = TranscriptDocument.model_validate_json(raw_path.read_text(encoding="utf-8"))
                repository.save_result(job_id, document)
                session.commit()
                self._publish(job_id, JobStatus.COMPLETED, 100, "finalize", "Transcript completed.")
            except ValidationError as exc:
                session.rollback()
                self._mark_failed(
                    repository,
                    session,
                    job_id,
                    error_code="FINALIZE_INVALID_RESULT",
                    message=str(exc),
                    progress=90,
                    stage="finalize",
                )
            except Exception:
                session.rollback()
                raise

    def mark_retry_exhausted(
        self,
        job_id: str,
        *,
        stage: str,
        retries: int,
        max_retries: int | None,
    ) -> None:
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                logger.warning("Retry exhausted for missing {} job {}.", stage, job_id)
                return
            if detail.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                return

            progress = detail.progress or (0 if stage == "prepare" else 90)
            message = f"{stage} failed after retries were exhausted."
            if max_retries is not None:
                message = f"{message} retries={retries}/{max_retries}"
            self._mark_failed(
                repository,
                session,
                job_id,
                error_code=f"{stage.upper()}_RETRY_EXHAUSTED",
                message=message,
                progress=progress,
                stage=stage,
            )

    def _set_progress(self, repository: JobRepository, session, job_id: str, *, progress: int) -> None:
        repository.update_job(job_id, status=JobStatus.PREPROCESSING, progress=progress)
        session.commit()
        self._publish(job_id, JobStatus.PREPROCESSING, progress, "prepare", "Job accepted for preprocessing.")

    def _mark_failed(
        self,
        repository: JobRepository,
        session,
        job_id: str,
        *,
        error_code: str,
        message: str,
        progress: int,
        stage: str,
    ) -> None:
        repository.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=progress,
            error_code=error_code,
            error_message=message,
        )
        session.commit()
        self._publish(job_id, JobStatus.FAILED, progress, stage, message)

    def _publish(self, job_id: str, status: JobStatus, progress: int, stage: str, message: str) -> None:
        try:
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
        except Exception:
            logger.exception("Failed to publish orchestrator event for job {}.", job_id)
