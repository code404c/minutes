from __future__ import annotations

import contextlib
import os
import tempfile
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
from minutes_inference.engines.base import InferenceEngine
from minutes_inference.engines.fake import FakeInferenceEngine
from minutes_inference.engines.remote_stt import RemoteSTTEngine, RemoteSTTError

# 处于这些状态的任务不需要再次执行转录
_NOOP_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.POSTPROCESSING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
}


class InferenceService:
    """
    推理服务类。

    该服务负责协调音频转录任务的执行。它从数据库中读取任务，调用远程 STT 服务，
    并更新任务状态。它还负责发布进度事件和处理错误。
    """

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker | None = None,
        event_bus: EventBus | None = None,
        queue_dispatcher: QueueDispatcher | None = None,
    ) -> None:
        """
        初始化推理服务。

        Args:
            settings: 全局配置。
            session_factory: 数据库会话工厂。
            event_bus: 事件总线，用于发布状态更新。
            queue_dispatcher: 队列分发器，用于将任务推送到后续阶段。
        """
        self.settings = settings
        self.session_factory = session_factory or create_session_factory(settings)
        self.event_bus = event_bus or EventBus(settings.redis_url)
        self.queue_dispatcher = queue_dispatcher or DramatiqQueueDispatcher()
        self._engine = self._create_engine()

    def _create_engine(self) -> InferenceEngine:
        """根据配置创建推理引擎（init 时调用一次）。"""
        if self.settings.fake_inference:
            return FakeInferenceEngine()
        return RemoteSTTEngine(
            base_url=self.settings.stt_base_url,
            api_key=self.settings.stt_api_key.get_secret_value() if self.settings.stt_api_key else None,
            timeout=self.settings.stt_timeout_seconds,
        )

    def transcribe_job(self, job_id: str) -> None:
        """
        执行转录任务的核心方法。

        Args:
            job_id: 任务的唯一标识符。
        """
        with self.session_factory() as session:
            repository = JobRepository(session)
            detail = repository.get_job(job_id)

            # 基础检查：任务是否存在、是否已经在处理中或已完成、是否缺少必要路径
            if detail is None:
                logger.warning("Transcription job {} no longer exists.", job_id)
                return
            if detail.status in _NOOP_STATUSES:
                logger.info("Skipping transcription for job {} in status {}.", job_id, detail.status.value)
                return
            if detail.normalized_path is None:
                logger.warning("Skipping transcription for job {} because normalized_path is missing.", job_id)
                return

            # 如果已经存在原始转录结果文件，则跳过推理，直接进入收尾阶段
            raw_path = Path(detail.output_dir) / "raw_transcript.json"
            if raw_path.exists():
                self._set_progress(repository, session, job_id, progress=85)
                self.queue_dispatcher.enqueue_finalize_job(job_id)
                return

            try:
                # 更新进度到 50%
                self._set_progress(repository, session, job_id, progress=50)

                # 调用引擎进行转录
                document = self._engine.transcribe(detail, Path(detail.normalized_path))
                # 将转录结果原子写入 JSON 文件（先写临时文件再 rename）
                tmp_fd, tmp_path = tempfile.mkstemp(dir=str(raw_path.parent), suffix=".tmp")
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                        f.write(document.model_dump_json(indent=2))
                    os.replace(tmp_path, str(raw_path))
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)
                    raise

                # 推理完成后更新进度到 85%
                self._set_progress(repository, session, job_id, progress=85)
            except RemoteSTTError as exc:
                # 处理 STT 服务返回的不可重试错误
                session.rollback()
                self._mark_failed(repository, session, job_id, exc.error_code, str(exc), progress=50)
                return
            except Exception:
                # 其他异常抛出，由外部（如 Dramatiq）处理重试
                session.rollback()
                raise

        # 将任务入队到 orchestrator 进行最终处理
        self.queue_dispatcher.enqueue_finalize_job(job_id)

    def close(self) -> None:
        """释放推理引擎持有的资源。"""
        self._engine.close()

    def mark_retry_exhausted(self, job_id: str, *, retries: int, max_retries: int | None) -> None:
        """
        当所有重试尝试都失败时调用的处理方法。
        """
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
        """更新任务进度并发布事件。"""
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
        """标记任务为失败并发布事件。"""
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
        """发布作业事件到事件总线（Redis）。"""
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
            logger.opt(exception=True).warning(
                "Non-fatal: failed to publish event for job {}, SSE clients may miss updates.", job_id
            )
