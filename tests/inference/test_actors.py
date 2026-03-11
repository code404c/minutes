from __future__ import annotations

import minutes_inference.actors as actors


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
