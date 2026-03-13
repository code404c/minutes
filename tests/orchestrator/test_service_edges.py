"""OrchestratorService 和 InferenceService 的边界场景测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minutes_core.constants import SYNC_TRANSCRIPTION_MAX_DURATION_MS, JobStatus
from minutes_core.media import MediaProbe
from minutes_core.models import JobRecord
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import TranscriptDocument

from .conftest import ServiceEnv, create_test_job

# ---------------------------------------------------------------------------
# OrchestratorService.prepare_job 边界测试
# ---------------------------------------------------------------------------


def test_prepare_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """prepare_job 对不存在的 job 应静默返回。"""
    e = service_env
    e.make_orchestrator().prepare_job("nonexistent-id")
    assert e.queue.transcribed == []


def test_prepare_job_skips_completed_job(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 应跳过 prepare。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    e.make_orchestrator().prepare_job(job_id)
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

    e.make_orchestrator().prepare_job(job_id)

    detail = e.get_job(job_id)
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

    e.make_orchestrator().prepare_job(job_id)
    assert e.queue.transcribed == [job_id]


# ---------------------------------------------------------------------------
# OrchestratorService.finalize_job 边界测试
# ---------------------------------------------------------------------------


def test_finalize_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """finalize_job 对不存在的 job 应静默返回。"""
    e = service_env
    e.make_orchestrator().finalize_job("nonexistent-id")


def test_finalize_job_missing_raw_transcript(service_env: ServiceEnv) -> None:
    """缺少 raw_transcript.json 应标记 FINALIZE_INPUT_MISSING。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=85)
        session.commit()

    e.make_orchestrator().finalize_job(job_id)

    detail = e.get_job(job_id)
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

    e.make_orchestrator().finalize_job(job_id)

    detail = e.get_job(job_id)
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
    e.make_orchestrator().finalize_job(job_id)
    assert len(e.events.events) == events_before


def test_finalize_job_skips_queued_status(service_env: ServiceEnv) -> None:
    """QUEUED 状态的 job 应跳过 finalize。"""
    e = service_env
    create_test_job(e)

    e.make_orchestrator().finalize_job(create_test_job(e))


# ---------------------------------------------------------------------------
# InferenceService.transcribe_job 边界测试
# ---------------------------------------------------------------------------


def test_transcribe_job_nonexistent_job_is_noop(service_env: ServiceEnv) -> None:
    """transcribe_job 对不存在的 job 应静默返回。"""
    e = service_env
    e.make_inference().transcribe_job("nonexistent-id")
    assert e.queue.finalized == []


def test_transcribe_job_skips_completed_job(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 应跳过 transcription。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    e.make_inference().transcribe_job(job_id)
    assert e.queue.finalized == []


def test_transcribe_job_skips_when_normalized_path_missing(service_env: ServiceEnv) -> None:
    """normalized_path 为 None 时应跳过 transcription。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.PREPROCESSING, progress=25)
        session.commit()

    e.make_inference().transcribe_job(job_id)
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

    e.make_inference().transcribe_job(job_id)
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

    e.make_inference().transcribe_job(job_id)

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
    e.make_inference().mark_retry_exhausted("nonexistent", retries=2, max_retries=2)


def test_mark_retry_exhausted_skips_already_completed(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 不应被标记为 FAILED。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    e.make_inference().mark_retry_exhausted(job_id, retries=2, max_retries=2)

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.COMPLETED


def test_mark_retry_exhausted_without_max_retries(service_env: ServiceEnv) -> None:
    """max_retries 为 None 时应正常标记失败。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=50)
        session.commit()

    e.make_inference().mark_retry_exhausted(job_id, retries=3, max_retries=None)

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "INFERENCE_RETRY_EXHAUSTED"


# ---------------------------------------------------------------------------
# OrchestratorService.prepare_job 未覆盖分支 (lines 126-128)
# ---------------------------------------------------------------------------


def test_prepare_job_unexpected_exception_rollbacks_and_reraises(service_env: ServiceEnv, monkeypatch) -> None:
    """probe_media 抛出非 MediaProcessingError 异常时应 rollback 并重新抛出。"""
    e = service_env
    job_id = create_test_job(e)

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: (_ for _ in ()).throw(RuntimeError("unexpected disk failure")),
    )

    with pytest.raises(RuntimeError, match="unexpected disk failure"):
        e.make_orchestrator().prepare_job(job_id)

    # 验证 job 状态未被破坏（rollback 后应保留原状态）
    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status != JobStatus.FAILED


# ---------------------------------------------------------------------------
# OrchestratorService.finalize_job 未覆盖分支 (lines 149-150)
# ---------------------------------------------------------------------------


def test_finalize_job_skips_when_result_already_exists_non_noop_status(service_env: ServiceEnv) -> None:
    """TRANSCRIBING 状态但已有 result 时应跳过 finalize（lines 148-150）。"""
    e = service_env
    job_id = create_test_job(e)

    # 手动设置 result_json 并将 status 改为 TRANSCRIBING（非 NOOP 状态）
    with e.session_factory() as session:
        record = session.get(JobRecord, job_id)
        assert record is not None
        doc = TranscriptDocument(
            job_id=job_id,
            language="zh",
            full_text="已有结果",
            segments=[],
            paragraphs=["已有结果"],
            speakers=[],
            model_profile=JobProfile.CN_MEETING,
        )
        record.result_json = doc.model_dump_json()
        record.status = JobStatus.TRANSCRIBING.value
        session.commit()

    events_before = len(e.events.events)
    e.make_orchestrator().finalize_job(job_id)

    # 应该跳过，不产生新事件
    assert len(e.events.events) == events_before
    # 状态应保持 TRANSCRIBING，未被改为其他
    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.TRANSCRIBING


# ---------------------------------------------------------------------------
# OrchestratorService.finalize_job 未覆盖分支 (lines 191-193)
# ---------------------------------------------------------------------------


def test_finalize_job_unexpected_exception_rollbacks_and_reraises(service_env: ServiceEnv, monkeypatch) -> None:
    """finalize_job 中出现非 ValidationError 的异常应 rollback 并重新抛出。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=85)
        session.commit()

    # 创建 raw_transcript.json，内容为合法 JSON
    raw_path = e.settings.artifacts_dir / job_id / "raw_transcript.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text('{"valid": "json"}', encoding="utf-8")

    # Mock TranscriptDocument.model_validate_json 使其抛出非 ValidationError
    monkeypatch.setattr(
        "minutes_orchestrator.services.TranscriptDocument.model_validate_json",
        lambda _text: (_ for _ in ()).throw(OSError("disk read error")),
    )

    with pytest.raises(OSError, match="disk read error"):
        e.make_orchestrator().finalize_job(job_id)


# ---------------------------------------------------------------------------
# OrchestratorService.mark_retry_exhausted 未覆盖分支 (lines 210-211, 213)
# ---------------------------------------------------------------------------


def test_orchestrator_mark_retry_exhausted_missing_job(service_env: ServiceEnv) -> None:
    """不存在的 job 应静默返回（lines 210-211）。"""
    e = service_env
    # 不应抛出异常
    e.make_orchestrator().mark_retry_exhausted(
        "nonexistent-orchestrator-job",
        stage="prepare",
        retries=2,
        max_retries=2,
    )


def test_orchestrator_mark_retry_exhausted_already_completed(service_env: ServiceEnv) -> None:
    """COMPLETED 状态的 job 不应被标记为 FAILED（line 213）。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.COMPLETED, progress=100)
        session.commit()

    e.make_orchestrator().mark_retry_exhausted(
        job_id,
        stage="prepare",
        retries=2,
        max_retries=2,
    )

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.COMPLETED


def test_orchestrator_mark_retry_exhausted_already_failed(service_env: ServiceEnv) -> None:
    """FAILED 状态的 job 不应被再次标记为 FAILED（line 213）。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=0,
            error_code="PREVIOUS_ERROR",
            error_message="previous failure",
        )
        session.commit()

    e.make_orchestrator().mark_retry_exhausted(
        job_id,
        stage="finalize",
        retries=2,
        max_retries=2,
    )

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    # 错误码应保持原样，不被覆盖
    assert detail.error_code == "PREVIOUS_ERROR"


def test_orchestrator_mark_retry_exhausted_already_canceled(service_env: ServiceEnv) -> None:
    """CANCELED 状态的 job 不应被标记为 FAILED（line 213）。"""
    e = service_env
    job_id = create_test_job(e)
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.CANCELED, progress=0)
        session.commit()

    e.make_orchestrator().mark_retry_exhausted(
        job_id,
        stage="prepare",
        retries=1,
        max_retries=2,
    )

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.CANCELED


# ---------------------------------------------------------------------------
# OrchestratorService._publish 异常处理 (lines 272-273)
# ---------------------------------------------------------------------------


def test_publish_exception_is_swallowed(service_env: ServiceEnv, monkeypatch) -> None:
    """_publish 中 event_bus.publish 抛出异常时应被吞掉，不影响主流程。"""
    e = service_env
    job_id = create_test_job(e)

    orchestrator = e.make_orchestrator()

    # 让 event_bus.publish 每次调用都抛出异常
    def exploding_publish(event):  # type: ignore[no-untyped-def]
        raise ConnectionError("Redis connection lost")

    orchestrator.event_bus = type("BrokenBus", (), {"publish": staticmethod(exploding_publish)})()

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: MediaProbe(duration_ms=3_000, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _s, output: output.write_bytes(b"normalized") or output,
    )

    # 即使 publish 异常，prepare_job 仍应正常完成
    orchestrator.prepare_job(job_id)

    detail = e.get_job(job_id)
    assert detail is not None
    assert detail.status == JobStatus.PREPROCESSING
    assert e.queue.transcribed == [job_id]
