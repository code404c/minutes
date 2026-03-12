"""跨测试模块共享的 builder、fake 和断言工具。"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from minutes_core.profiles import JobProfile
from minutes_core.schemas import Segment, TranscriptDocument

# ---------------------------------------------------------------------------
# Fake 队列与事件总线（Orchestrator / Inference 测试共用）
# ---------------------------------------------------------------------------


class RecordingQueue:
    """记录所有入队调用的 Fake 队列分发器。"""

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
    """记录所有发布事件的 Fake 事件总线。

    统一记录为 3-tuple ``(stage, status_value, progress)``。
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str, int]] = []

    def publish(self, event) -> None:  # type: ignore[no-untyped-def]
        self.events.append((event.stage, event.status.value, event.progress))

    def has_event(self, status_value: str, stage: str) -> bool:
        """便捷检查：忽略 progress，兼容旧的 (status, stage) 断言模式。"""
        return any(s == stage and st == status_value for s, st, _ in self.events)


# ---------------------------------------------------------------------------
# Builder 工具
# ---------------------------------------------------------------------------


def build_transcript_document(job_id: str, *, text: str = "大家好，今天讨论项目排期。") -> TranscriptDocument:
    """构建一个标准的测试用 TranscriptDocument。"""
    return TranscriptDocument(
        job_id=job_id,
        language="zh",
        full_text=text,
        paragraphs=[text],
        segments=[
            Segment(
                start_ms=0,
                end_ms=1_800,
                speaker_id="spk-1",
                text="大家好，今天讨论项目排期。",
                confidence=0.98,
            ),
            Segment(
                start_ms=1_800,
                end_ms=3_600,
                speaker_id="spk-2",
                text="先看预算，再看风险。",
                confidence=0.95,
            ),
        ],
        speakers=[],
        model_profile=JobProfile.CN_MEETING,
    )


# ---------------------------------------------------------------------------
# Assertion / 提取工具
# ---------------------------------------------------------------------------


def extract_job_id(payload: dict[str, Any]) -> str:
    """从 API 响应中提取 job ID，支持 id / job_id / jobId 三种键名。"""
    for key in ("id", "job_id", "jobId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise AssertionError(f"response does not contain a job identifier: {payload}")


def error_message(payload: dict[str, Any]) -> str:
    """从错误响应中提取可读的错误信息。"""
    if "detail" in payload:
        detail = payload["detail"]
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            for key in ("message", "error", "detail"):
                value = detail.get(key)
                if isinstance(value, str):
                    return value
    if "error" in payload:
        error_obj = payload["error"]
        if isinstance(error_obj, str):
            return error_obj
        if isinstance(error_obj, dict):
            for key in ("message", "detail", "error"):
                value = error_obj.get(key)
                if isinstance(value, str):
                    return value
    return str(payload)


def assert_reasonable_error(response, *, status: HTTPStatus | tuple[HTTPStatus, ...], contains: str) -> None:  # type: ignore[no-untyped-def]
    """断言 HTTP 响应为指定状态码且包含预期错误信息片段。"""
    expected = status if isinstance(status, tuple) else (status,)
    assert response.status_code in {item.value for item in expected}
    payload = response.json()
    assert contains.lower() in error_message(payload).lower()
