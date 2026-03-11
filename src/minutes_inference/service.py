from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings
from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory
from minutes_core.events import EventBus
from minutes_core.queue import DramatiqQueueDispatcher, QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobEvent
from minutes_inference.engines.fake import FakeInferenceEngine
from minutes_inference.engines.funasr_engine import FunASREngine
from minutes_inference.model_pool import TTLModelPool


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
                raise KeyError(job_id)
            if detail.normalized_path is None:
                raise RuntimeError(f"Job {job_id} is missing normalized_path.")

            try:
                repository.update_job(job_id, status=JobStatus.TRANSCRIBING, progress=50)
                self._publish(job_id, JobStatus.TRANSCRIBING, 50, "transcribe", "ASR inference started.")

                engine = FakeInferenceEngine() if self.settings.fake_inference else FunASREngine(
                    settings=self.settings,
                    model_pool=self.model_pool,
                )
                document = engine.transcribe(detail, Path(detail.normalized_path))
                raw_path = Path(detail.output_dir) / "raw_transcript.json"
                raw_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
                repository.update_job(job_id, status=JobStatus.TRANSCRIBING, progress=85)
                self._publish(job_id, JobStatus.TRANSCRIBING, 85, "transcribe", "ASR inference finished.")
            except Exception as exc:
                repository.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    progress=50,
                    error_code="INFERENCE_FAILED",
                    error_message=str(exc),
                )
                self._publish(job_id, JobStatus.FAILED, 50, "transcribe", str(exc))
                return

        self.queue_dispatcher.enqueue_finalize_job(job_id)

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
