from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from minutes_core.config import Settings, get_settings
from minutes_core.models import Base


def create_engine_from_url(database_url: str, *, sqlite_busy_timeout_ms: int = 5000) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
        if database_url.endswith(":memory:") or database_url == "sqlite://":
            engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **engine_kwargs)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute(f"PRAGMA busy_timeout={sqlite_busy_timeout_ms};")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    db_path = settings.database_url.removeprefix("sqlite:///")
    if settings.database_url.startswith("sqlite:///") and db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine_from_url(settings.database_url, sqlite_busy_timeout_ms=settings.sqlite_busy_timeout_ms)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def init_database_cli() -> None:
    settings = get_settings()
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])
    with session_factory() as session:
        session.execute(text("SELECT 1"))
        session.commit()
