from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from minutes_core.config import Settings, get_settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.events import EventBus
from minutes_core.logging import configure_logging
from minutes_core.queue import DramatiqQueueDispatcher, QueueDispatcher
from minutes_core.storage import StorageManager
from minutes_gateway.routers.jobs import router as jobs_router
from minutes_gateway.routers.openai import router as openai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理。
    在应用启动时初始化数据库，在关闭时清理资源（如 Redis 连接）。
    """
    init_database(app.state.session_factory.kw["bind"])
    try:
        yield
    finally:
        # 关闭事件总线连接
        close = getattr(app.state.event_bus, "close", None)
        if callable(close):
            close()


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    queue_dispatcher: QueueDispatcher | None = None,
    event_bus: EventBus | None = None,
) -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。

    该工厂函数负责：
    1. 加载配置和配置日志。
    2. 初始化数据库会话工厂、队列分发器和事件总线。
    3. 将这些共享对象存储在 app.state 中，以便在路由依赖中使用。
    4. 注册中间件和路由。
    """
    settings = settings or get_settings()
    # 配置结构化日志
    configure_logging(service_name="gateway", log_level=settings.log_level, serialize=settings.log_json)

    # 核心组件初始化
    session_factory = session_factory or create_session_factory(settings)
    queue_dispatcher = queue_dispatcher or DramatiqQueueDispatcher()
    event_bus = event_bus or EventBus(settings.redis_url)

    app = FastAPI(
        title="Minutes Gateway",
        lifespan=lifespan,
    )

    # 将组件挂载到应用状态空间，方便后续通过 Dependency Injection 获取
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.queue_dispatcher = queue_dispatcher
    app.state.event_bus = event_bus
    app.state.storage_manager = StorageManager(settings)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """
        请求 ID 中间件。
        为每个请求生成或传递 x-request-id，便于在分布式系统中追踪日志。
        """
        request.state.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.get("/health")
    async def health() -> JSONResponse:
        """健康检查接口。"""
        return JSONResponse({"status": "ok", "service": "gateway"})

    # 包含具体的 API 业务路由
    app.include_router(jobs_router)
    app.include_router(openai_router)
    return app


def main() -> None:
    """网关服务入口。"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "minutes_gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )
