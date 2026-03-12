"""SSE 端点 /jobs/{job_id}/events 的单元测试。"""

from __future__ import annotations

import json
from http import HTTPStatus

from minutes_core.constants import JobStatus
from minutes_core.schemas import JobEvent

from .conftest import build_transcript_document


def test_stream_events_returns_404_for_missing_job(gateway_harness_factory) -> None:
    """不存在的 job 应返回 404。"""
    with gateway_harness_factory() as harness:
        response = harness.client.get("/api/v1/jobs/non-existent-job/events")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_stream_events_sends_initial_snapshot(gateway_harness_factory) -> None:
    """SSE 流应先发送一个包含当前状态的 snapshot 事件。"""
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.TRANSCRIBING, progress=50)
        response = harness.client.get(f"/api/v1/jobs/{job.id}/events")

    assert response.status_code == HTTPStatus.OK
    # sse-starlette 返回 text/event-stream
    assert "text/event-stream" in response.headers.get("content-type", "")

    # 解析 SSE 文本
    events = _parse_sse_events(response.text)
    assert len(events) >= 1

    first = events[0]
    assert first["event"] == "job"
    data = json.loads(first["data"])
    assert data["event"] == "snapshot"
    assert data["job_id"] == job.id
    assert data["status"] == JobStatus.TRANSCRIBING.value
    assert data["progress"] == 50


def test_stream_events_sends_snapshot_for_queued_job(gateway_harness_factory) -> None:
    """QUEUED 状态的 job 也应该正常返回 snapshot。"""
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.QUEUED, progress=0)
        response = harness.client.get(f"/api/v1/jobs/{job.id}/events")

    assert response.status_code == HTTPStatus.OK
    events = _parse_sse_events(response.text)
    assert len(events) >= 1
    data = json.loads(events[0]["data"])
    assert data["status"] == JobStatus.QUEUED.value
    assert data["progress"] == 0


def test_stream_events_snapshot_includes_error_code_when_failed(gateway_harness_factory) -> None:
    """FAILED 状态的 job snapshot 应包含 error_code payload。"""
    with gateway_harness_factory() as harness:
        job = harness.create_job(
            status=JobStatus.FAILED,
            progress=50,
            error_code="INFERENCE_RETRY_EXHAUSTED",
            error_message="retries exhausted",
        )
        response = harness.client.get(f"/api/v1/jobs/{job.id}/events")

    assert response.status_code == HTTPStatus.OK
    events = _parse_sse_events(response.text)
    data = json.loads(events[0]["data"])
    assert data["payload"]["error_code"] == "INFERENCE_RETRY_EXHAUSTED"


def test_stream_events_yields_subsequent_events_from_event_bus(gateway_harness_factory) -> None:
    """FakeEventBus 中预存的消息应作为后续事件被推送。"""
    with gateway_harness_factory() as harness:
        job = harness.create_job(status=JobStatus.PREPROCESSING, progress=25)

        # 在 FakeEventBus 中预填充一条后续事件
        update_event = JobEvent(
            event="job.updated",
            job_id=job.id,
            status=JobStatus.TRANSCRIBING,
            progress=50,
            stage="transcribe",
            message="ASR inference started.",
        )
        harness.event_bus.enqueue_message(job.id, update_event.model_dump_json())

        response = harness.client.get(f"/api/v1/jobs/{job.id}/events")

    assert response.status_code == HTTPStatus.OK
    events = _parse_sse_events(response.text)
    # 应有 snapshot + 1 条后续事件
    assert len(events) == 2

    # 第一个是 snapshot
    snapshot_data = json.loads(events[0]["data"])
    assert snapshot_data["event"] == "snapshot"

    # 第二个是后续推送的事件
    update_data = json.loads(events[1]["data"])
    assert update_data["event"] == "job.updated"
    assert update_data["status"] == JobStatus.TRANSCRIBING.value
    assert update_data["progress"] == 50


def test_stream_events_completed_job_has_empty_payload(gateway_harness_factory) -> None:
    """COMPLETED 状态的 job snapshot 的 payload 应为空 dict。"""
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/events")

    assert response.status_code == HTTPStatus.OK
    events = _parse_sse_events(response.text)
    data = json.loads(events[0]["data"])
    assert data["status"] == JobStatus.COMPLETED.value
    assert data["payload"] == {}


def _parse_sse_events(text: str) -> list[dict[str, str]]:
    """解析 SSE 文本格式，返回事件列表。兼容 CRLF 和 LF 换行。"""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
        elif line == "" and current:
            if "data" in current:
                events.append(current)
            current = {}
    if current and "data" in current:
        events.append(current)
    return events
