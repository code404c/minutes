"""Inference retry exhausted 测试。"""

from __future__ import annotations

from minutes_core.constants import JobStatus
from minutes_core.repositories import JobRepository
from tests.orchestrator.conftest import ServiceEnv, create_test_job


def test_mark_retry_exhausted_marks_inference_job_failed(service_env: ServiceEnv) -> None:
    e = service_env
    job_id = create_test_job(e, job_id="job-123")
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.TRANSCRIBING, progress=50)
        session.commit()

    e.make_inference().mark_retry_exhausted("job-123", retries=2, max_retries=2)

    detail = e.get_job("job-123")
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "INFERENCE_RETRY_EXHAUSTED"
    assert e.events.has_event("failed", "transcribe")
