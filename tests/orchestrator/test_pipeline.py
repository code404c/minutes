"""音频预处理流水线测试。"""

from __future__ import annotations

from pathlib import Path

from minutes_core.constants import JobStatus
from minutes_core.media import MediaProbe, MediaProcessingError
from minutes_core.repositories import JobRepository
from minutes_inference.service import InferenceService
from minutes_orchestrator.services import OrchestratorService

from .conftest import create_test_job


def test_prepare_job_normalizes_media_and_dispatches_transcription(service_env, monkeypatch) -> None:
    e = service_env
    job_id = create_test_job(e["session_factory"], e["tmp_path"], e["media_path"])

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: MediaProbe(duration_ms=4_000, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _s, output: output.write_bytes(b"normalized") or output,
    )

    service = OrchestratorService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )
    service.prepare_job(job_id)

    with e["session_factory"]() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.PREPROCESSING
    assert detail.duration_ms == 4_000
    assert detail.normalized_path is not None
    assert Path(detail.normalized_path).exists()
    assert e["queue"].transcribed == [job_id]
    assert ("prepare", "preprocessing", 25) in e["events"].events


def test_end_to_end_pipeline_completes_with_fake_inference(service_env, monkeypatch) -> None:
    e = service_env
    job_id = create_test_job(e["session_factory"], e["tmp_path"], e["media_path"])

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: MediaProbe(duration_ms=3_000, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _s, output: output.write_bytes(b"normalized") or output,
    )

    orchestrator = OrchestratorService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )
    inference = InferenceService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )

    orchestrator.prepare_job(job_id)
    inference.transcribe_job(job_id)
    orchestrator.finalize_job(job_id)

    with e["session_factory"]() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.COMPLETED
    assert detail.result is not None
    assert "Fake transcript" in detail.result.full_text
    assert e["queue"].transcribed == [job_id]
    assert e["queue"].finalized == [job_id]
    assert ("finalize", "completed", 100) in e["events"].events


def test_prepare_job_marks_failure_when_media_processing_errors(service_env, monkeypatch) -> None:
    e = service_env
    # 用一个"坏"媒体文件覆盖
    broken_path = e["tmp_path"] / "broken.m4a"
    broken_path.write_bytes(b"broken")
    job_id = create_test_job(e["session_factory"], e["tmp_path"], broken_path)

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: (_ for _ in ()).throw(MediaProcessingError("ffprobe failed")),
    )

    service = OrchestratorService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )
    service.prepare_job(job_id)

    with e["session_factory"]() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "MEDIA_PROCESSING_FAILED"
    assert e["queue"].transcribed == []
    assert ("prepare", "failed", 0) in e["events"].events


def test_pipeline_stage_reentry_after_completion_is_noop(service_env, monkeypatch) -> None:
    e = service_env
    job_id = create_test_job(e["session_factory"], e["tmp_path"], e["media_path"])

    monkeypatch.setattr(
        "minutes_orchestrator.services.probe_media",
        lambda _p: MediaProbe(duration_ms=3_000, format_name="wav"),
    )
    monkeypatch.setattr(
        "minutes_orchestrator.services.transcode_to_wav",
        lambda _s, output: output.write_bytes(b"normalized") or output,
    )

    orchestrator = OrchestratorService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )
    inference = InferenceService(
        settings=e["settings"],
        session_factory=e["session_factory"],
        event_bus=e["events"],
        queue_dispatcher=e["queue"],
    )

    orchestrator.prepare_job(job_id)
    inference.transcribe_job(job_id)
    orchestrator.finalize_job(job_id)

    queue_snapshot = (list(e["queue"].transcribed), list(e["queue"].finalized))

    orchestrator.prepare_job(job_id)
    inference.transcribe_job(job_id)
    orchestrator.finalize_job(job_id)

    with e["session_factory"]() as session:
        detail = JobRepository(session).get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.COMPLETED
    assert queue_snapshot == (e["queue"].transcribed, e["queue"].finalized)
