from __future__ import annotations

from pathlib import Path

from loguru import logger
from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings
from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory
from minutes_core.events import EventBus
from minutes_core.queue import DramatiqQueueDispatcher, QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobEvent
from minutes_inference.engines.fake import FakeInferenceEngine
from minutes_inference.engines.funasr_engine import FunASREngine, FunASRUnavailableError
from minutes_inference.model_pool import TTLModelPool

_NOOP_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.POSTPROCESSING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
}


class InferenceService:
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
        self.model_pool = TTLModelPool(settings.model_ttl_seconds)

    def transcribe_job(self, job_id: str) -> None:
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                logger.warning("Transcription job {} no longer exists.", job_id)
                return
            if detail.status in _NOOP_STATUSES:
                logger.info("Skipping transcription for job {} in status {}.", job_id, detail.status.value)
                return
            if detail.normalized_path is None:
                logger.warning("Skipping transcription for job {} because normalized_path is missing.", job_id)
                return

            raw_path = Path(detail.output_dir) / "raw_transcript.json"
            if raw_path.exists():
                self._set_progress(repository, session, job_id, progress=85)
                self.queue_dispatcher.enqueue_finalize_job(job_id)
                return

            try:
                self._set_progress(repository, session, job_id, progress=50)

                engine = (
                    FakeInferenceEngine()
                    if self.settings.fake_inference
                    else FunASREngine(
                        settings=self.settings,
                        model_pool=self.model_pool,
                    )
                )
                document = engine.transcribe(detail, Path(detail.normalized_path))
                raw_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
                self._set_progress(repository, session, job_id, progress=85)
            except FunASRUnavailableError as exc:
                session.rollback()
                self._mark_failed(repository, session, job_id, "INFERENCE_BACKEND_UNAVAILABLE", str(exc), progress=50)
                return
            except Exception:
                session.rollback()
                raise

        self.queue_dispatcher.enqueue_finalize_job(job_id)

    def mark_retry_exhausted(self, job_id: str, *, retries: int, max_retries: int | None) -> None:
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)
            if detail is None:
                logger.warning("Retry exhausted for missing transcription job {}.", job_id)
                return
            if detail.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                return
            message = "ASR inference failed after retries were exhausted."
            if max_retries is not None:
                message = f"{message} retries={retries}/{max_retries}"
            self._mark_failed(
                repository,
                session,
                job_id,
                "INFERENCE_RETRY_EXHAUSTED",
                message,
                progress=detail.progress or 50,
            )

    def _set_progress(self, repository: JobRepository, session, job_id: str, *, progress: int) -> None:
        message = "ASR inference started." if progress == 50 else "ASR inference finished."
        repository.update_job(job_id, status=JobStatus.TRANSCRIBING, progress=progress)
        session.commit()
        self._publish(job_id, JobStatus.TRANSCRIBING, progress, "transcribe", message)

    def _mark_failed(
        self,
        repository: JobRepository,
        session,
        job_id: str,
        error_code: str,
        message: str,
        *,
        progress: int,
    ) -> None:
        repository.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=progress,
            error_code=error_code,
            error_message=message,
        )
        session.commit()
        self._publish(job_id, JobStatus.FAILED, progress, "transcribe", message)

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
            logger.exception("Failed to publish inference event for job {}.", job_id)
