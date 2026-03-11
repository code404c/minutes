from __future__ import annotations

from http import HTTPStatus

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository

from .conftest import build_transcript_document


def _error_message(payload: dict[str, object]) -> str:
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        for key in ("message", "error", "detail"):
            value = detail.get(key)
            if isinstance(value, str):
                return value
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        for key in ("message", "detail", "error"):
            value = error.get(key)
            if isinstance(value, str):
                return value
    return str(payload)


def _assert_reasonable_error(response, *, status: HTTPStatus | tuple[HTTPStatus, ...], contains: str) -> None:  # type: ignore[no-untyped-def]
    expected = status if isinstance(status, tuple) else (status,)
    assert response.status_code in {item.value for item in expected}
    assert contains.lower() in _error_message(response.json()).lower()


def _post_transcription(client, *, stream: bool | None = None):  # type: ignore[no-untyped-def]
    data = {"model": JobProfile.CN_MEETING.value}
    if stream is not None:
        data["stream"] = "true" if stream else "false"
    return client.post(
        "/v1/audio/transcriptions",
        data=data,
        files={"file": ("meeting.wav", b"fake-audio-bytes", "audio/wav")},
    )


def test_openai_transcriptions_rejects_stream_true(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        response = _post_transcription(harness.client, stream=True)

    _assert_reasonable_error(response, status=HTTPStatus.BAD_REQUEST, contains="stream")


def test_openai_transcriptions_returns_timeout_error(gateway_harness_factory) -> None:
    with gateway_harness_factory(sync_wait_timeout_s=1) as harness:
        response = _post_transcription(harness.client)

    _assert_reasonable_error(response, status=HTTPStatus.GATEWAY_TIMEOUT, contains="timed out")


def test_openai_transcriptions_returns_failed_job_error(gateway_harness_factory) -> None:
    def fail_job(session_factory, _stage: str, job_id: str) -> None:  # type: ignore[no-untyped-def]
        with session_factory() as session:
            repo = JobRepository(session)
            repo.update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=100,
                error_code="transcription_failed",
                error_message="transcription backend crashed",
            )
            session.commit()

    with gateway_harness_factory(on_dispatch=fail_job) as harness:
        response = _post_transcription(harness.client)

    _assert_reasonable_error(
        response,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        contains="transcription backend crashed",
    )


def test_openai_transcriptions_returns_success_response(gateway_harness_factory) -> None:
    def complete_job(session_factory, stage: str, job_id: str) -> None:
        if stage != "prepare":
            return
        with session_factory() as session:
            repo = JobRepository(session)
            repo.save_result(job_id, build_transcript_document(job_id, text="同步转写完成"))
            session.commit()

    with gateway_harness_factory(on_dispatch=complete_job) as harness:
        response = _post_transcription(harness.client)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"text": "同步转写完成"}
