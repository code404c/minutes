from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from loguru import logger
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from minutes_core.config import Settings, get_settings
from minutes_core.models import Base


def create_engine_from_url(database_url: str, *, sqlite_busy_timeout_ms: int = 5000) -> Engine:
    """
    根据给定的数据库 URL 创建 SQLAlchemy Engine 实例。
    针对 SQLite 进行了特殊的并发优化配置（如 WAL 模式）。
    """
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True}

    # 如果使用的是 SQLite 数据库
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False  # 允许在不同线程中使用同一连接
        engine_kwargs["connect_args"] = connect_args
        # 如果是内存数据库，使用静态线程池以防数据库被自动删除
        if database_url.endswith(":memory:") or database_url == "sqlite://":
            engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **engine_kwargs)

    # 针对 SQLite 连接的运行时 Pragmas 配置
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # 开启 WAL（Write-Ahead Logging）模式以提高并发性能
            cursor.execute("PRAGMA journal_mode=WAL;")
            # 设置重试等待时长，防止繁忙时抛出 'database is locked'
            cursor.execute(f"PRAGMA busy_timeout={sqlite_busy_timeout_ms};")
            # 同步模式设为 NORMAL，平衡性能与安全性
            cursor.execute("PRAGMA synchronous=NORMAL;")
            # 强制开启外键约束检查
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """
    创建一个会话工厂对象，用于产生新的数据库会话。
    会自动创建 SQLite 数据库所在的父目录。
    """
    settings = settings or get_settings()
    db_path = settings.database_url.removeprefix("sqlite:///")
    if settings.database_url.startswith("sqlite:///") and db_path:
        # 确保数据库文件所在的目录已存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine_from_url(settings.database_url, sqlite_busy_timeout_ms=settings.sqlite_busy_timeout_ms)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_database(engine: Engine) -> None:
    """
    根据模型定义创建所有的数据库表（如果表尚不存在）。
    """
    logger.info("Initializing database tables via {}", engine.url)
    Base.metadata.create_all(engine)


def get_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """
    FastAPI 依赖项生成器，提供一个新的数据库会话，并在使用完后关闭。
    """
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def init_database_cli() -> None:
    """
    命令行初始化工具，用于创建表并验证数据库连接。
    """
    settings = get_settings()
    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])
    with session_factory() as session:
        # 执行一个简单的查询以验证数据库是否可用
        session.execute(text("SELECT 1"))
        session.commit()
