"""InferenceService 分支覆盖补充测试。

覆盖目标:
- line 46-47: job 不存在时 warning 退出
- line 52-53: job 在 NOOP 状态时 skip
- line 57-59: raw_transcript.json 已存在时直接跳过
- line 76-82: RemoteSTTError 非重试错误处理
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minutes_core.config import Settings
from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory, init_database
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate
from minutes_inference.engines.remote_stt import RemoteSTTError
from minutes_inference.service import InferenceService


class RecordingQueue:
    """记录 enqueue 调用的 fake dispatcher。"""

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
    """记录事件发布的 fake event bus。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def publish(self, event) -> None:
        self.events.append((event.status.value, event.stage))


def _make_service(tmp_path: Path) -> tuple[InferenceService, Settings, RecordingQueue, RecordingEventBus]:
    """构造 InferenceService 及其依赖。"""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        storage_root=tmp_path,
        redis_url="redis://unused:6379/0",
        fake_inference=True,
    )
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])

    queue = RecordingQueue()
    event_bus = RecordingEventBus()
    service = InferenceService(
        settings=settings,
        session_factory=session_factory,
        event_bus=event_bus,
        queue_dispatcher=queue,
    )
    return service, settings, queue, event_bus


def _create_job(
    session_factory,
    tmp_path: Path,
    *,
    job_id: str = "job-svc-1",
    status: JobStatus = JobStatus.TRANSCRIBING,
    normalized_path: str | None = None,
) -> str:
    """在数据库中创建一个 job 并返回 job_id。"""
    output_dir = tmp_path / "artifacts" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with session_factory() as session:
        repo = JobRepository(session)
        created = repo.create_job(
            JobCreate(
                job_id=job_id,
                source_filename="meeting.wav",
                source_content_type="audio/wav",
                source_path=str(tmp_path / "meeting.wav"),
                output_dir=str(output_dir),
                profile=JobProfile.CN_MEETING,
                language="zh",
            )
        )
        repo.update_job(
            created.id,
            status=status,
            progress=50,
            normalized_path=normalized_path,
        )
        session.commit()
    return job_id


class TestTranscribeJobMissingJob:
    """测试 job 不存在时 warning 退出 (line 46-47)。"""

    def test_nonexistent_job_returns_silently(self, tmp_path: Path) -> None:
        """验证对不存在的 job_id 调用 transcribe_job 不抛异常，直接返回。"""
        service, _, queue, event_bus = _make_service(tmp_path)

        service.transcribe_job("nonexistent-job-id")

        assert len(queue.finalized) == 0
        assert len(event_bus.events) == 0


class TestTranscribeJobNoopStatuses:
    """测试 job 在 NOOP 状态时 skip (line 52-53)。"""

    @pytest.mark.parametrize(
        "status",
        [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.QUEUED],
        ids=["completed", "failed", "queued"],
    )
    def test_noop_status_is_skipped(self, tmp_path: Path, status: JobStatus) -> None:
        """验证 NOOP 状态的 job 被跳过。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        sf = create_session_factory(settings)
        job_id = f"job-{status.value}"
        _create_job(sf, tmp_path, job_id=job_id, status=status, normalized_path="/fake/path.wav")

        service.transcribe_job(job_id)

        assert len(queue.finalized) == 0
        assert len(event_bus.events) == 0


class TestTranscribeJobMissingNormalizedPath:
    """测试 normalized_path 为 None 时 skip (line 52-53 分支)。"""

    def test_missing_normalized_path_skips(self, tmp_path: Path) -> None:
        """验证 normalized_path 为空时跳过转录。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        sf = create_session_factory(settings)
        _create_job(sf, tmp_path, job_id="job-no-norm", status=JobStatus.TRANSCRIBING, normalized_path=None)

        service.transcribe_job("job-no-norm")

        assert len(queue.finalized) == 0
        assert len(event_bus.events) == 0


class TestTranscribeJobRawTranscriptExists:
    """测试 raw_transcript.json 已存在时直接跳过 (line 57-59)。"""

    def test_existing_raw_transcript_skips_inference(self, tmp_path: Path) -> None:
        """验证当 raw_transcript.json 已存在时，跳过推理并直接 enqueue finalize。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        sf = create_session_factory(settings)

        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"fake-audio")

        job_id = _create_job(
            sf,
            tmp_path,
            job_id="job-existing-raw",
            status=JobStatus.TRANSCRIBING,
            normalized_path=str(normalized),
        )

        # 预先创建 raw_transcript.json
        output_dir = tmp_path / "artifacts" / job_id
        raw_path = output_dir / "raw_transcript.json"
        raw_path.write_text(json.dumps({"text": "pre-existing"}), encoding="utf-8")

        service.transcribe_job(job_id)

        # 应该直接跳到 finalize，不重新推理
        assert job_id in queue.finalized
        # 应该发布了 progress=85 的事件
        assert ("transcribing", "transcribe") in event_bus.events


class TestTranscribeJobRemoteSTTError:
    """测试 RemoteSTTError 非重试错误处理 (line 76-82)。"""

    @pytest.mark.parametrize(
        "job_id,error_msg,status_code,error_code",
        [
            ("job-stt-err", "STT bad request: invalid model", 400, "INFERENCE_BAD_REQUEST"),
            ("job-auth-err", "STT authentication failed", 401, "INFERENCE_AUTH_FAILED"),
        ],
        ids=["bad-request", "auth-error"],
    )
    def test_remote_stt_error_marks_failed(
        self, tmp_path: Path, job_id: str, error_msg: str, status_code: int, error_code: str
    ) -> None:
        """验证 RemoteSTTError 导致 job 标记为 FAILED，不抛异常，不 enqueue finalize。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        service.settings = settings.model_copy(update={"fake_inference": False, "stt_base_url": "http://stt:8000"})

        sf = create_session_factory(settings)

        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"fake-audio")

        _create_job(
            sf,
            tmp_path,
            job_id=job_id,
            status=JobStatus.TRANSCRIBING,
            normalized_path=str(normalized),
        )

        stt_error = RemoteSTTError(
            error_msg,
            status_code=status_code,
            error_code=error_code,
        )

        with patch("minutes_inference.service.RemoteSTTEngine") as mock_engine_cls:
            mock_engine_instance = MagicMock()
            mock_engine_instance.transcribe.side_effect = stt_error
            mock_engine_cls.return_value = mock_engine_instance

            service.transcribe_job(job_id)

        # 不应 enqueue finalize
        assert job_id not in queue.finalized

        # 应标记为 FAILED
        with sf() as session:
            detail = JobRepository(session).get_job(job_id)

        assert detail is not None
        assert detail.status == JobStatus.FAILED
        assert detail.error_code == error_code

        # 应发布 failed 事件
        assert ("failed", "transcribe") in event_bus.events


class TestTranscribeJobGenericExceptionRollback:
    """测试未预期异常的 rollback + re-raise 分支 (line 80-82)。"""

    def test_unexpected_error_rolls_back_and_reraises(self, tmp_path: Path) -> None:
        """验证非 RemoteSTTError 的异常会 rollback session 并重新抛出。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        service.settings = settings.model_copy(update={"fake_inference": False, "stt_base_url": "http://stt:8000"})

        sf = create_session_factory(settings)

        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"fake-audio")

        _create_job(
            sf,
            tmp_path,
            job_id="job-generic-err",
            status=JobStatus.TRANSCRIBING,
            normalized_path=str(normalized),
        )

        # mock RemoteSTTEngine.transcribe 抛出非 RemoteSTTError 的异常
        with patch("minutes_inference.service.RemoteSTTEngine") as mock_engine_cls:
            mock_engine_instance = MagicMock()
            mock_engine_instance.transcribe.side_effect = RuntimeError("Unexpected CUDA OOM")
            mock_engine_cls.return_value = mock_engine_instance

            with pytest.raises(RuntimeError, match="Unexpected CUDA OOM"):
                service.transcribe_job("job-generic-err")

        # 不应 enqueue finalize
        assert "job-generic-err" not in queue.finalized

        # job 不应被标记为 FAILED（由 Dramatiq 重试机制处理）
        with sf() as session:
            detail = JobRepository(session).get_job("job-generic-err")
        assert detail is not None
        assert detail.status == JobStatus.TRANSCRIBING


class TestMarkRetryExhaustedBranches:
    """测试 mark_retry_exhausted 中的早期退出分支 (line 91-92, 94)。"""

    def test_missing_job_returns_silently(self, tmp_path: Path) -> None:
        """验证对不存在的 job_id 调用 mark_retry_exhausted 不抛异常。"""
        service, _, queue, event_bus = _make_service(tmp_path)

        service.mark_retry_exhausted("nonexistent-job", retries=1, max_retries=3)

        assert len(event_bus.events) == 0

    @pytest.mark.parametrize(
        "status",
        [JobStatus.COMPLETED, JobStatus.FAILED],
        ids=["already-completed", "already-failed"],
    )
    def test_terminal_status_is_skipped(self, tmp_path: Path, status: JobStatus) -> None:
        """验证终态 job 调用 mark_retry_exhausted 时跳过。"""
        service, settings, queue, event_bus = _make_service(tmp_path)
        sf = create_session_factory(settings)
        job_id = f"job-{status.value}"
        _create_job(sf, tmp_path, job_id=job_id, status=status, normalized_path="/fake.wav")

        service.mark_retry_exhausted(job_id, retries=3, max_retries=3)

        with sf() as session:
            detail = JobRepository(session).get_job(job_id)
        assert detail is not None
        assert detail.status == status
        assert len(event_bus.events) == 0


class TestPublishEventFailure:
    """测试 _publish 中 event_bus.publish 抛异常时的异常捕获 (line 145-146)。"""

    def test_event_bus_failure_does_not_propagate(self, tmp_path: Path) -> None:
        """验证 event_bus.publish 抛异常时，不会中断 transcribe_job 流程。"""
        (
            service,
            settings,
            queue,
            _,
        ) = _make_service(tmp_path)
        sf = create_session_factory(settings)

        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"fake-audio")

        _create_job(
            sf,
            tmp_path,
            job_id="job-evt-err",
            status=JobStatus.TRANSCRIBING,
            normalized_path=str(normalized),
        )

        # 使用会抛异常的 event bus
        failing_bus = MagicMock()
        failing_bus.publish.side_effect = ConnectionError("Redis connection lost")
        service.event_bus = failing_bus

        # transcribe_job 应该正常完成，不抛异常
        service.transcribe_job("job-evt-err")

        # 尽管 event_bus 出错，finalize 仍应被 enqueue
        assert "job-evt-err" in queue.finalized
