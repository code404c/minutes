from __future__ import annotations

import importlib
import inspect
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from minutes_core.config import Settings, get_settings
from minutes_core.constants import JobStatus
from minutes_core.db import create_session_factory, init_database
from minutes_core.media import MediaProbe
from minutes_core.profiles import JobProfile
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, JobDetail, Segment, TranscriptDocument
from minutes_core.storage import StorageManager

DispatchCallback = Callable[[sessionmaker[Session], str, str], None]


class FakeDispatcher:
    def __init__(self, on_dispatch: DispatchCallback | None = None) -> None:
        self.on_dispatch = on_dispatch
        self.calls: list[tuple[str, str]] = []

    def enqueue_prepare_job(self, job_id: str) -> None:
        self._record("prepare", job_id)

    def enqueue_finalize_job(self, job_id: str) -> None:
        self._record("finalize", job_id)

    def enqueue_transcription_job(self, job_id: str) -> None:
        self._record("transcription", job_id)

    def _record(self, stage: str, job_id: str) -> None:
        self.calls.append((stage, job_id))
        if self.on_dispatch is not None:
            self.on_dispatch(self.session_factory, stage, job_id)

    session_factory: sessionmaker[Session]


class FakeEventBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, event: Any) -> None:
        self.published.append((str(getattr(event, "job_id", "")), str(getattr(event, "event", ""))))

    async def subscribe(self, _job_id: str):  # type: ignore[no-untyped-def]
        if False:
            yield ""


@dataclass(slots=True)
class GatewayHarness:
    app: Any
    client: TestClient
    dispatcher: FakeDispatcher
    event_bus: FakeEventBus
    session_factory: sessionmaker[Session]
    settings: Settings
    storage_manager: StorageManager
    created_job_ids: list[str] = field(default_factory=list)

    def create_job(
        self,
        *,
        status: JobStatus = JobStatus.QUEUED,
        progress: int = 0,
        sync_mode: bool = False,
        result: TranscriptDocument | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        language: str = "zh",
        profile: JobProfile = JobProfile.CN_MEETING,
    ) -> JobDetail:
        source_dir = self.settings.uploads_dir / f"seed-{uuid.uuid4().hex[:8]}"
        artifact_dir = self.settings.artifacts_dir / f"seed-{uuid.uuid4().hex[:8]}"
        source_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "meeting.wav"
        source_path.write_bytes(b"seed-audio")

        with self.session_factory() as session:
            repo = JobRepository(session)
            created = repo.create_job(
                JobCreate(
                    source_filename=source_path.name,
                    source_content_type="audio/wav",
                    source_path=str(source_path),
                    output_dir=str(artifact_dir),
                    profile=profile,
                    language=language,
                    hotwords=["预算", "风险"],
                    sync_mode=sync_mode,
                )
            )
            session.commit()
            self.created_job_ids.append(created.id)
            if result is not None:
                stored = repo.save_result(created.id, result.model_copy(update={"job_id": created.id}))
                session.commit()
            elif status is not JobStatus.QUEUED or progress or error_code or error_message:
                stored = repo.update_job(
                    created.id,
                    status=status,
                    progress=progress,
                    error_code=error_code,
                    error_message=error_message,
                    language=language,
                )
                session.commit()
            else:
                stored = created
        return stored


def build_transcript_document(job_id: str, *, text: str = "大家好，今天讨论项目排期。") -> TranscriptDocument:
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


def extract_job_id(payload: dict[str, Any]) -> str:
    for key in ("id", "job_id", "jobId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise AssertionError(f"response does not contain a job identifier: {payload}")


def error_message(payload: dict[str, Any]) -> str:
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
    expected = status if isinstance(status, tuple) else (status,)
    assert response.status_code in {item.value for item in expected}
    payload = response.json()
    assert contains.lower() in error_message(payload).lower()


def _purge_gateway_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "minutes_gateway" or module_name.startswith("minutes_gateway."):
            sys.modules.pop(module_name)


def _import_gateway_app_module() -> Any:
    _purge_gateway_modules()
    try:
        return importlib.import_module("minutes_gateway.app")
    except ModuleNotFoundError as exc:
        if exc.name in {"minutes_gateway", "minutes_gateway.app"}:
            pytest.skip("minutes_gateway.app:create_app is not implemented yet")
        raise


def _settings_for(tmp_path: Path, *, sync_wait_timeout_s: int) -> Settings:
    data_root = tmp_path / uuid.uuid4().hex
    return Settings(
        database_url="sqlite://",
        storage_root=data_root,
        redis_url="redis://localhost:6379/15",
        sync_wait_timeout_s=sync_wait_timeout_s,
        gateway_public_base_url="http://testserver",
        log_json=False,
    )


def _override_dependencies(
    app: Any,
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    dispatcher: FakeDispatcher,
    storage_manager: StorageManager,
    event_bus: FakeEventBus,
) -> None:
    def provide_settings() -> Settings:
        return settings

    def provide_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def provide_repository() -> Iterator[JobRepository]:
        session = session_factory()
        try:
            yield JobRepository(session)
        finally:
            session.close()

    def provide_session_factory() -> sessionmaker[Session]:
        return session_factory

    def provide_dispatcher() -> FakeDispatcher:
        return dispatcher

    def provide_storage_manager() -> StorageManager:
        return storage_manager

    def provide_event_bus() -> FakeEventBus:
        return event_bus

    provider_map = {
        "get_settings": provide_settings,
        "provide_settings": provide_settings,
        "get_session": provide_session,
        "get_db": provide_session,
        "get_db_session": provide_session,
        "get_session_factory": provide_session_factory,
        "get_db_session_factory": provide_session_factory,
        "get_job_repository": provide_repository,
        "get_repository": provide_repository,
        "get_repository_factory": lambda: JobRepository,
        "get_job_repository_factory": lambda: JobRepository,
        "get_dispatcher": provide_dispatcher,
        "get_queue_dispatcher": provide_dispatcher,
        "get_storage_manager": provide_storage_manager,
        "get_event_bus": provide_event_bus,
    }

    candidate_modules = ["minutes_gateway.app", "minutes_gateway.dependencies"]
    candidate_modules.extend(
        name
        for name in sys.modules
        if name.startswith("minutes_gateway.routers.") or name.startswith("minutes_gateway.api.")
    )

    for module_name in candidate_modules:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for dependency_name, provider in provider_map.items():
            dependency = getattr(module, dependency_name, None)
            if callable(dependency):
                app.dependency_overrides[dependency] = provider

    for attribute_name in (
        "settings",
        "session_factory",
        "dispatcher",
        "queue_dispatcher",
        "storage_manager",
        "event_bus",
    ):
        if attribute_name == "settings":
            setattr(app.state, attribute_name, settings)
        elif attribute_name == "session_factory":
            setattr(app.state, attribute_name, session_factory)
        elif attribute_name in {"dispatcher", "queue_dispatcher"}:
            setattr(app.state, attribute_name, dispatcher)
        elif attribute_name == "storage_manager":
            setattr(app.state, attribute_name, storage_manager)
        elif attribute_name == "event_bus":
            setattr(app.state, attribute_name, event_bus)


def _build_app(create_app: Callable[..., Any], **available_kwargs: Any) -> Any:
    signature = inspect.signature(create_app)
    kwargs = {
        parameter_name: value
        for parameter_name, value in available_kwargs.items()
        if parameter_name in signature.parameters
    }
    if "testing" in signature.parameters and "testing" not in kwargs:
        kwargs["testing"] = True
    return create_app(**kwargs)


@pytest.fixture
def gateway_harness_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    @contextmanager
    def factory(
        *,
        sync_wait_timeout_s: int = 1,
        probe_duration_ms: int = 8_000,
        on_dispatch: DispatchCallback | None = None,
    ) -> Iterator[GatewayHarness]:
        settings = _settings_for(tmp_path, sync_wait_timeout_s=sync_wait_timeout_s)
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

        dispatcher = FakeDispatcher(on_dispatch=on_dispatch)
        event_bus = FakeEventBus()
        session_factory = create_session_factory(settings)
        dispatcher.session_factory = session_factory
        init_database(session_factory.kw["bind"])
        storage_manager = StorageManager(settings)

        monkeypatch.setenv("MINUTES_DATABASE_URL", settings.database_url)
        monkeypatch.setenv("MINUTES_STORAGE_ROOT", str(settings.storage_root))
        monkeypatch.setenv("MINUTES_REDIS_URL", settings.redis_url)
        monkeypatch.setenv("MINUTES_SYNC_WAIT_TIMEOUT_S", str(settings.sync_wait_timeout_s))
        monkeypatch.setenv("MINUTES_GATEWAY_PUBLIC_BASE_URL", settings.gateway_public_base_url)
        get_settings.cache_clear()

        import minutes_core.media as media_module
        import minutes_core.queue as queue_module

        monkeypatch.setattr(
            media_module,
            "probe_media",
            lambda _path: MediaProbe(duration_ms=probe_duration_ms, format_name="wav"),
        )
        monkeypatch.setattr(queue_module, "configure_broker", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(queue_module, "DramatiqQueueDispatcher", lambda: dispatcher)

        app_module = _import_gateway_app_module()
        create_app = getattr(app_module, "create_app", None)
        if not callable(create_app):
            pytest.skip("minutes_gateway.app:create_app is not implemented yet")

        app = _build_app(
            create_app,
            settings=settings,
            session_factory=session_factory,
            dispatcher=dispatcher,
            queue_dispatcher=dispatcher,
            storage_manager=storage_manager,
            event_bus=event_bus,
            testing=True,
        )
        _override_dependencies(
            app,
            settings=settings,
            session_factory=session_factory,
            dispatcher=dispatcher,
            storage_manager=storage_manager,
            event_bus=event_bus,
        )

        with TestClient(app) as client:
            yield GatewayHarness(
                app=app,
                client=client,
                dispatcher=dispatcher,
                event_bus=event_bus,
                session_factory=session_factory,
                settings=settings,
                storage_manager=storage_manager,
            )

    return factory
