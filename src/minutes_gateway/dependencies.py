from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from minutes_core.config import Settings
from minutes_core.events import EventBus
from minutes_core.queue import QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.storage import StorageManager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def verify_api_key(request: Request) -> None:
    settings: Settings = request.app.state.settings
    configured_key = settings.api_key.get_secret_value() if settings.api_key else None
    if configured_key is None:
        return
    header = request.headers.get("authorization", "")
    expected = f"Bearer {configured_key}"
    if header != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid API key.",
        )


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_db_session(request: Request) -> Generator[Session, None, None]:
    factory = get_session_factory(request)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_job_repository(session: Session = Depends(get_db_session)) -> JobRepository:
    return JobRepository(session)


def get_storage_manager(request: Request) -> StorageManager:
    return request.app.state.storage_manager


def get_queue_dispatcher(request: Request) -> QueueDispatcher:
    return request.app.state.queue_dispatcher


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus
