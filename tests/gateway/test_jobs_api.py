from __future__ import annotations

from http import HTTPStatus

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile

from .conftest import build_transcript_document, extract_job_id


def test_health_returns_healthy_status(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = harness.client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert isinstance(payload, dict)
    if "status" in payload:
        assert str(payload["status"]).lower() in {"ok", "healthy", "pass"}
    else:
        assert payload.get("ok") is True or payload.get("healthy") is True


def test_post_jobs_creates_job_and_dispatches_work(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = harness.client.post(
            "/api/v1/jobs",
            files={"file": ("meeting.wav", b"fake-audio-bytes", "audio/wav")},
        )

        assert response.status_code == HTTPStatus.ACCEPTED
        payload = response.json()
        job_id = extract_job_id(payload)

        assert payload["status"] == JobStatus.QUEUED.value
        assert ("prepare", job_id) in harness.dispatcher.calls

        with harness.session_factory() as session:
            from minutes_core.repositories import JobRepository

            persisted = JobRepository(session).get_job(job_id)

        assert persisted is not None
        assert persisted.id == job_id
        assert persisted.source_filename == "meeting.wav"
        assert persisted.profile == JobProfile.CN_MEETING


def test_get_job_returns_current_job_state(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.TRANSCRIBING, progress=55)
        response = harness.client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["id"] == job.id
    assert payload["status"] == JobStatus.TRANSCRIBING.value
    assert payload["progress"] == 55
    assert payload["profile"] == JobProfile.CN_MEETING.value


def test_get_job_transcript_returns_completed_document(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/transcript")

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["job_id"] == job.id
    assert payload["language"] == "zh"
    assert payload["full_text"] == "大家好，今天讨论项目排期。"
    assert [segment["text"] for segment in payload["segments"]] == [
        "大家好，今天讨论项目排期。",
        "先看预算，再看风险。",
    ]


def test_get_job_returns_404_for_missing_job(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = harness.client.get("/api/v1/jobs/missing-job")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_transcript_returns_404_for_missing_job(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = harness.client.get("/api/v1/jobs/nonexistent-id/transcript")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_transcript_returns_409_when_job_is_not_ready(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.TRANSCRIBING, progress=50)
        response = harness.client.get(f"/api/v1/jobs/{job.id}/transcript")

    assert response.status_code == HTTPStatus.CONFLICT


def test_export_returns_404_for_missing_job(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = harness.client.get("/api/v1/jobs/missing-job/export?format=txt")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_export_returns_409_when_job_is_not_ready(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.TRANSCRIBING, progress=50)
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=txt")

    assert response.status_code == HTTPStatus.CONFLICT
