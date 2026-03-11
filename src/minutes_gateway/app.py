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
    init_database(app.state.session_factory.kw["bind"])
    yield


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    queue_dispatcher: QueueDispatcher | None = None,
    event_bus: EventBus | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name="gateway", log_level=settings.log_level, serialize=settings.log_json)
    session_factory = session_factory or create_session_factory(settings)
    queue_dispatcher = queue_dispatcher or DramatiqQueueDispatcher()
    event_bus = event_bus or EventBus(settings.redis_url)

    app = FastAPI(
        title="Minutes Gateway",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.queue_dispatcher = queue_dispatcher
    app.state.event_bus = event_bus
    app.state.storage_manager = StorageManager(settings)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "gateway"})

    app.include_router(jobs_router)
    app.include_router(openai_router)
    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "minutes_gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )
