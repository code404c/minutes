"""OpenAI 兼容接口 /v1/audio/transcriptions 的多格式响应测试。"""

from __future__ import annotations

from http import HTTPStatus

from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository

from .conftest import build_transcript_document


def _complete_job(session_factory, stage: str, job_id: str) -> None:
    """在 dispatch 回调中直接完成任务（模拟 worker 处理结果）。"""
    if stage != "prepare":
        return
    with session_factory() as session:
        repo = JobRepository(session)
        repo.save_result(job_id, build_transcript_document(job_id))
        session.commit()


def _post_transcription(client, *, response_format: str = "json", stream: bool = False):
    data = {"model": JobProfile.CN_MEETING.value, "response_format": response_format}
    if stream:
        data["stream"] = "true"
    return client.post(
        "/v1/audio/transcriptions",
        data=data,
        files={"file": ("meeting.wav", b"fake-audio-bytes", "audio/wav")},
    )


def test_openai_transcriptions_text_format(gateway_harness_factory) -> None:
    """response_format=text 应返回纯文本。"""
    with gateway_harness_factory(on_dispatch=_complete_job) as harness:
        response = _post_transcription(harness.client, response_format="text")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/plain")
    assert "大家好，今天讨论项目排期。" in response.text


def test_openai_transcriptions_srt_format(gateway_harness_factory) -> None:
    """response_format=srt 应返回 SRT 格式。"""
    with gateway_harness_factory(on_dispatch=_complete_job) as harness:
        response = _post_transcription(harness.client, response_format="srt")

    assert response.status_code == HTTPStatus.OK
    assert "application/x-subrip" in response.headers["content-type"]
    assert "00:00:00,000 -->" in response.text


def test_openai_transcriptions_vtt_format(gateway_harness_factory) -> None:
    """response_format=vtt 应返回 WebVTT 格式。"""
    with gateway_harness_factory(on_dispatch=_complete_job) as harness:
        response = _post_transcription(harness.client, response_format="vtt")

    assert response.status_code == HTTPStatus.OK
    assert "text/vtt" in response.headers["content-type"]
    assert response.text.startswith("WEBVTT")


def test_openai_transcriptions_verbose_json_format(gateway_harness_factory) -> None:
    """response_format=verbose_json 应返回完整的 TranscriptDocument JSON。"""
    with gateway_harness_factory(on_dispatch=_complete_job) as harness:
        response = _post_transcription(harness.client, response_format="verbose_json")

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert "segments" in payload
    assert "full_text" in payload
    assert payload["language"] == "zh"


def test_openai_transcriptions_json_format_returns_simple_text(gateway_harness_factory) -> None:
    """response_format=json (默认) 应返回 {"text": "..."} 格式。"""
    with gateway_harness_factory(on_dispatch=_complete_job) as harness:
        response = _post_transcription(harness.client, response_format="json")

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert "text" in payload
    assert payload["text"] == "大家好，今天讨论项目排期。"


def test_openai_transcriptions_duration_limit_exceeded(gateway_harness_factory) -> None:
    """同步模式下超过时长限制的 job 应返回 422。"""
    from minutes_core.constants import JobStatus

    def fail_with_duration_exceeded(session_factory, _stage: str, job_id: str) -> None:
        with session_factory() as session:
            repo = JobRepository(session)
            repo.update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=0,
                error_code="SYNC_DURATION_LIMIT_EXCEEDED",
                error_message="Synchronous OpenAI-compatible transcription only supports media up to 15 minutes.",
            )
            session.commit()

    with gateway_harness_factory(on_dispatch=fail_with_duration_exceeded) as harness:
        response = _post_transcription(harness.client)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
