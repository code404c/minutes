"""Orchestrator retry exhausted 测试。"""

from __future__ import annotations

from minutes_core.constants import JobStatus
from minutes_core.repositories import JobRepository

from .conftest import ServiceEnv, create_test_job


def test_mark_retry_exhausted_marks_prepare_job_failed(service_env: ServiceEnv) -> None:
    e = service_env
    job_id = create_test_job(e, job_id="job-prepare")
    with e.session_factory() as session:
        JobRepository(session).update_job(job_id, status=JobStatus.PREPROCESSING, progress=5)
        session.commit()

    e.make_orchestrator().mark_retry_exhausted("job-prepare", stage="prepare", retries=2, max_retries=2)

    detail = e.get_job("job-prepare")
    assert detail is not None
    assert detail.status == JobStatus.FAILED
    assert detail.error_code == "PREPARE_RETRY_EXHAUSTED"
    assert e.events.has_event("failed", "prepare")
