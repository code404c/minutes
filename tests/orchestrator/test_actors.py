"""Orchestrator actors 单元测试。"""

from __future__ import annotations

import minutes_orchestrator.actors as actors

# ---------------------------------------------------------------------------
# _extract_retry_payload
# ---------------------------------------------------------------------------


def test_extract_retry_payload_valid_data() -> None:
    """正常参数应正确提取 job_id、retries 和 max_retries。"""
    message_data = {"args": ["job-abc"], "actor_name": "prepare_job_actor"}
    retry_data = {"retries": 1, "max_retries": 3}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id == "job-abc"
    assert retries == 1
    assert max_retries == 3


def test_extract_retry_payload_missing_args() -> None:
    """args 为 None 时应返回 job_id=None。"""
    message_data: dict[str, object] = {"actor_name": "prepare_job_actor"}
    retry_data = {"retries": 0, "max_retries": 2}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id is None
    assert retries == 0
    assert max_retries == 2


def test_extract_retry_payload_empty_args() -> None:
    """args 为空列表时应返回 job_id=None。"""
    message_data: dict[str, object] = {"args": [], "actor_name": "prepare_job_actor"}
    retry_data = {"retries": 1, "max_retries": 2}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id is None


def test_extract_retry_payload_non_string_first_arg() -> None:
    """args[0] 非字符串时应返回 job_id=None。"""
    message_data: dict[str, object] = {"args": [12345], "actor_name": "prepare_job_actor"}
    retry_data = {"retries": 0, "max_retries": 2}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id is None


def test_extract_retry_payload_missing_retry_data_keys() -> None:
    """retry_data 缺少 retries/max_retries 时应使用默认值。"""
    message_data: dict[str, object] = {"args": ["job-xyz"]}
    retry_data: dict[str, int] = {}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id == "job-xyz"
    assert retries == 0
    assert max_retries is None


def test_extract_retry_payload_tuple_args() -> None:
    """args 为 tuple 时也应能正确提取。"""
    message_data: dict[str, object] = {"args": ("job-tuple",)}
    retry_data = {"retries": 2, "max_retries": 5}

    job_id, retries, max_retries = actors._extract_retry_payload(message_data, retry_data)

    assert job_id == "job-tuple"
    assert retries == 2
    assert max_retries == 5


# ---------------------------------------------------------------------------
# get_orchestrator_service (singleton)
# ---------------------------------------------------------------------------


def test_get_orchestrator_service_creates_singleton(monkeypatch) -> None:
    """单例模式应确保只创建一个 OrchestratorService 实例。"""
    created: list[object] = []

    class FakeOrchestratorService:
        def __init__(self, *, settings) -> None:  # type: ignore[no-untyped-def]
            self.settings = settings
            created.append(self)

    monkeypatch.setattr(actors, "OrchestratorService", FakeOrchestratorService)
    monkeypatch.setattr(actors, "_service", None)

    first = actors.get_orchestrator_service()
    second = actors.get_orchestrator_service()

    assert first is second
    assert len(created) == 1


# ---------------------------------------------------------------------------
# actor 函数直接调用（通过 .fn 获取底层函数）
# ---------------------------------------------------------------------------


def test_prepare_job_actor_calls_service(monkeypatch) -> None:
    """prepare_job_actor 应调用 service.prepare_job。"""
    captured: list[str] = []

    class FakeService:
        def prepare_job(self, job_id: str) -> None:
            captured.append(job_id)

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    actors.prepare_job_actor.fn("job-prep-001")

    assert captured == ["job-prep-001"]


def test_finalize_job_actor_calls_service(monkeypatch) -> None:
    """finalize_job_actor 应调用 service.finalize_job。"""
    captured: list[str] = []

    class FakeService:
        def finalize_job(self, job_id: str) -> None:
            captured.append(job_id)

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    actors.finalize_job_actor.fn("job-fin-001")

    assert captured == ["job-fin-001"]


# ---------------------------------------------------------------------------
# handle_orchestrator_retry_exhausted
# ---------------------------------------------------------------------------


def test_retry_exhausted_prepare_job(monkeypatch) -> None:
    """prepare_job_actor 重试耗尽应调用 mark_retry_exhausted(stage='prepare')。"""
    captured: dict[str, object] = {}

    class FakeService:
        def mark_retry_exhausted(self, job_id: str, *, stage: str, retries: int, max_retries: int | None) -> None:
            captured["job_id"] = job_id
            captured["stage"] = stage
            captured["retries"] = retries
            captured["max_retries"] = max_retries

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data = {"args": ["job-retry-1"], "actor_name": actors.prepare_job_actor.actor_name}
    retry_data = {"retries": 2, "max_retries": 2}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert captured == {"job_id": "job-retry-1", "stage": "prepare", "retries": 2, "max_retries": 2}


def test_retry_exhausted_finalize_job(monkeypatch) -> None:
    """finalize_job_actor 重试耗尽应调用 mark_retry_exhausted(stage='finalize')。"""
    captured: dict[str, object] = {}

    class FakeService:
        def mark_retry_exhausted(self, job_id: str, *, stage: str, retries: int, max_retries: int | None) -> None:
            captured["job_id"] = job_id
            captured["stage"] = stage
            captured["retries"] = retries
            captured["max_retries"] = max_retries

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data = {"args": ["job-retry-2"], "actor_name": actors.finalize_job_actor.actor_name}
    retry_data = {"retries": 1, "max_retries": 3}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert captured == {"job_id": "job-retry-2", "stage": "finalize", "retries": 1, "max_retries": 3}


def test_retry_exhausted_unknown_actor(monkeypatch) -> None:
    """未知的 actor_name 应直接返回，不调用 mark_retry_exhausted。"""
    called = False

    class FakeService:
        def mark_retry_exhausted(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal called
            called = True

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data = {"args": ["job-unknown"], "actor_name": "some_unknown_actor"}
    retry_data = {"retries": 2, "max_retries": 2}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert not called


def test_retry_exhausted_invalid_payload_missing_job_id(monkeypatch) -> None:
    """args 缺失导致 job_id=None 时应直接返回。"""
    called = False

    class FakeService:
        def mark_retry_exhausted(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal called
            called = True

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data: dict[str, object] = {"actor_name": "prepare_job_actor"}
    retry_data = {"retries": 1, "max_retries": 2}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert not called


def test_retry_exhausted_invalid_payload_missing_actor_name(monkeypatch) -> None:
    """actor_name 缺失时应直接返回。"""
    called = False

    class FakeService:
        def mark_retry_exhausted(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal called
            called = True

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data: dict[str, object] = {"args": ["job-no-actor"]}
    retry_data = {"retries": 1, "max_retries": 2}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert not called


def test_retry_exhausted_non_string_actor_name(monkeypatch) -> None:
    """actor_name 非字符串时应直接返回。"""
    called = False

    class FakeService:
        def mark_retry_exhausted(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal called
            called = True

    monkeypatch.setattr(actors, "get_orchestrator_service", lambda: FakeService())

    message_data: dict[str, object] = {"args": ["job-abc"], "actor_name": 12345}
    retry_data = {"retries": 1, "max_retries": 2}

    actors.handle_orchestrator_retry_exhausted.fn(message_data, retry_data)

    assert not called
