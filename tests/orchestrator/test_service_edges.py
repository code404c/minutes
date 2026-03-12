"""OrchestratorService 和 InferenceService 的边界场景测试。"""

from __future__ import annotations

import json
from pathlib import Path

from minutes_core.constants import SYNC_TRANSCRIPTION_MAX_DURATION_MS, JobStatus
from minutes_core.media import MediaProbe
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import TranscriptDocument
from minutes_inference.service import InferenceService
from minutes_orchestrator.services import OrchestratorService

from .conftest import ServiceEnv, create_test_job

# ---------------------------------------------------------------------------
# OrchestratorService.prepare_job 边界测试
# ---------------------------------------------------------------------------


def test_prepare_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """prepare_job 对不存在的 job 应静默返回。"""
    e = service_env
    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.prepare_job("nonexistent-id")
    assert e.queue.transcribed == []


def test_prepare_job_skips_completed_job(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 应跳过 prepare。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.prepare_job(job_id)
    assert e.queue.transcribed == []


def test_prepare_job_sync_mode_duration_limit_exceeded(service_env: ServiceEnv, monkeypatch) -> None:
    """同步模式下超过时长限制应标记 FAILED。"""
    e = service_env
    job_id = create_test_job(e, sync_mode=True)

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: MediaProbe(duration_ms=SYNC_TRANSCRIPTION_MAX_DURATION_MS + 1, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _s, output: output.write_bytes(b"normalized") or output,
    )

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.prepare_job(job_id)

    with e.session_factory() as session:
        detail = JobRepository(session).get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "SYNC_DURATION_LIMIT_EXCEEDED"
    assert e.queue.transcribed == []


def test_prepare_job_reentry_with_existing_normalized_path(service_env: ServiceEnv) -> None:
    """PREPROCESSING 状态且 normalized_path 已存在时应直接跳到 transcription。"""
    e = service_env
    job_id = create_test_job(e)
    normalized = e.tmp_path / "artifacts" / job_id / "normalized.wav"
    normalized.write_bytes(b"normalized")

    with e.session_factory() as session:
        JobRepository(session).update_job(
            job_id,
            status=JobStatus.PREPROCESSING,
            progress=25,
            normalized_path=str(normalized),
        )
        session.commit()

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.prepare_job(job_id)
    assert e.queue.transcribed == [job_id]


# ---------------------------------------------------------------------------
# OrchestratorService.finalize_job 边界测试
# ---------------------------------------------------------------------------


def test_finalize_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """finalize_job 对不存在的 job 应静默返回。"""
    e = service_env
    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.finalize_job("nonexistent-id")


def test_finalize_job_missing_raw_transcript(service_env: ServiceEnv) -> None:
    """缺少 raw_transcript.json 应标记 FINALIZE_INPUT_MISSING。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=85)
        session.commit()

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.finalize_job(job_id)

    with e.session_factory() as session:
        detail = JobRepository(session).get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "FINALIZE_INPUT_MISSING"


def test_finalize_job_invalid_json_marks_failed(service_env: ServiceEnv) -> None:
    """raw_transcript.json 格式无效应标记 FINALIZE_INVALID_RESULT。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=85)
        session.commit()

    raw_path = e.settings.artifacts_dir / job_id / "raw_transcript.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text('{"invalid": "not a TranscriptDocument"}', encoding="utf-8")

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.finalize_job(job_id)

    with e.session_factory() as session:
        detail = JobRepository(session).get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "FINALIZE_INVALID_RESULT"


def test_finalize_job_skips_when_result_already_exists(service_env: ServiceEnv) -> None:
    """已经有 result 的 job 应跳过 finalize。"""
    e = service_env
    job_id = create_test_job(e)
    doc = TranscriptDocument(
        job_id=job_id,
        language="zh",
        full_text="已有结果",
        segments=[],
        paragraphs=["已有结果"],
        speakers=[],
        model_profile=JobProfile.CN_MEETING,
    )
    with e.session_factory() as session:
        JobRepository(session).save_result(job_id, doc)
        session.commit()

    events_before = len(e.events.events)
    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.finalize_job(job_id)
    assert len(e.events.events) == events_before


def test_finalize_job_skips_queued_status(service_env: ServiceEnv) -> None:
    """QUEUED 状态的 job 应跳过 finalize。"""
    e = service_env
    job_id = create_test_job(e)

    service = OrchestratorService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.finalize_job(job_id)


# ---------------------------------------------------------------------------
# InferenceService.transcribe_job 边界测试
# ---------------------------------------------------------------------------


def test_transcribe_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """transcribe_job 对不存在的 job 应静默返回。"""
    e = service_env
    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.transcribe_job("nonexistent-id")
    assert e.queue.finalized == []


def test_transcribe_job_skips_completed_job(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 应跳过 transcription。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.transcribe_job(job_id)
    assert e.queue.finalized == []


def test_transcribe_job_skips_when_normalized_path_missing(service_env: ServiceEnv) -> None:
    """normalized_path 为 None 时应跳过 transcription。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.PREPROCESSING, progress=25)
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.transcribe_job(job_id)
    assert e.queue.finalized == []


def test_transcribe_job_skips_when_raw_transcript_exists(service_env: ServiceEnv) -> None:
    """raw_transcript.json 已存在时应跳过推理，直接 enqueue finalize。"""
    e = service_env
    job_id = create_test_job(e)
    normalized = e.tmp_path / "artifacts" / job_id / "normalized.wav"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_bytes(b"normalized")

    raw_path = Path(e.tmp_path / "artifacts" / job_id / "raw_transcript.json")
    raw_path.write_text('{"already": "done"}', encoding="utf-8")

    with e.session_factory() as session:
        JobRepository(session).update_job(
            job_id,
            status=JobStatus.TRANSCRIBING,
            progress=50,
            normalized_path=str(normalized),
        )
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.transcribe_job(job_id)
    assert e.queue.finalized == [job_id]


def test_transcribe_job_fake_inference_produces_result(service_env: ServiceEnv) -> None:
    """使用 fake inference 应成功产生 raw_transcript.json。"""
    e = service_env
    job_id = create_test_job(e)
    normalized = e.tmp_path / "artifacts" / job_id / "normalized.wav"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_bytes(b"normalized")

    with e.session_factory() as session:
        JobRepository(session).update_job(
            job_id,
            status=JobStatus.PREPROCESSING,
            progress=25,
            normalized_path=str(normalized),
            duration_ms=3000,
        )
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.transcribe_job(job_id)

    raw_path = e.tmp_path / "artifacts" / job_id / "raw_transcript.json"
    assert raw_path.exists()
    content = json.loads(raw_path.read_text(encoding="utf-8"))
    assert "Fake transcript" in content["full_text"]
    assert e.queue.finalized == [job_id]


# ---------------------------------------------------------------------------
# InferenceService.mark_retry_exhausted 边界测试
# ---------------------------------------------------------------------------


def test_mark_retry_exhausted_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """不存在的 job 应静默返回。"""
    e = service_env
    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.mark_retry_exhausted("nonexistent", retries=2, max_retries=2)


def test_mark_retry_exhausted_skips_already_completed(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 不应被标记为 FAILED。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.mark_retry_exhausted(job_id, retries=2, max_retries=2)

    with e.session_factory() as session:
        detail = JobRepository(session).get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.COMPLETED


def test_mark_retry_exhausted_without_max_retries(service_env: ServiceEnv) -> None:
    """max_retries 为 None 时应正常标记失败。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=50)
        session.commit()

    service = InferenceService(
        settings=e.settings,
        session_factory=e.session_factory,
        event_bus=e.events,
        queue_dispatcher=e.queue,
    )
    service.mark_retry_exhausted(job_id, retries=3, max_retries=None)

    with e.session_factory() as session:
        detail = JobRepository(session).get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "INFERENCE_RETRY_EXHAUSTED"
