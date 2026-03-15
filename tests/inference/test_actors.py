from __future__ import annotations

import minutes_inference.actors as actors
from minutes_core.logging import job_id_var


def test_get_inference_service_returns_process_singleton(monkeypatch) -> None:
    created: list[object] = []

    class FakeInferenceService:
        def __init__(self, *, settings) -> None:  # type: ignore[no-untyped-def]
            self.settings = settings
            created.append(self)

        def transcribe_job(self, _job_id: str) -> None:
            return None

    monkeypatch.setattr(actors, "InferenceService", FakeInferenceService)
    monkeypatch.setattr(actors, "_service", None)

    first = actors.get_inference_service()
    second = actors.get_inference_service()

    assert first is second
    assert len(created) == 1


def test_handle_inference_retry_exhausted_forwards_retry_metadata(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeService:
        def mark_retry_exhausted(self, job_id: str, *, retries: int, max_retries: int | None) -> None:
            captured["job_id"] = job_id
            captured["retries"] = retries
            captured["max_retries"] = max_retries

    monkeypatch.setattr(actors, "get_inference_service", lambda: FakeService())

    actors.handle_inference_retry_exhausted({"args": ["job-123"]}, {"retries": 2, "max_retries": 2})

    assert captured == {"job_id": "job-123", "retries": 2, "max_retries": 2}


def test_transcribe_job_actor_calls_service(monkeypatch) -> None:
    """验证 transcribe_job_actor 调用 get_inference_service().transcribe_job(job_id)。"""
    captured: list[str] = []

    class FakeService:
        def transcribe_job(self, job_id: str) -> None:
            captured.append(job_id)

    monkeypatch.setattr(actors, "get_inference_service", lambda: FakeService())

    actors.transcribe_job_actor("job-abc")

    assert captured == ["job-abc"]


def test_transcribe_job_actor_binds_job_id(monkeypatch) -> None:
    """验证 transcribe_job_actor 将 job_id 绑定到日志上下文。"""

    class FakeService:
        def transcribe_job(self, job_id: str) -> None:
            pass

    monkeypatch.setattr(actors, "get_inference_service", lambda: FakeService())
    job_id_var.set(None)

    actors.transcribe_job_actor("job-ctx-inf-001")

    assert job_id_var.get() == "job-ctx-inf-001"


def test_retry_exhausted_invalid_payload_returns_early(monkeypatch) -> None:
    """验证 job_id 为 None 时（无效 payload），handler 提前返回，不调用 mark_retry_exhausted。"""
    called = False

    class FakeService:
        def mark_retry_exhausted(self, job_id: str, *, retries: int, max_retries: int | None) -> None:
            nonlocal called
            called = True

    monkeypatch.setattr(actors, "get_inference_service", lambda: FakeService())

    # args 为空列表，无法提取 job_id
    actors.handle_inference_retry_exhausted({"args": []}, {"retries": 1, "max_retries": 2})
    assert not called

    # args 不存在
    actors.handle_inference_retry_exhausted({}, {"retries": 0, "max_retries": 1})
    assert not called

    # args 中第一个元素不是 str
    actors.handle_inference_retry_exhausted({"args": [123]}, {"retries": 0, "max_retries": 1})
    assert not called
