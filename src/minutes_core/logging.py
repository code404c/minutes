from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

from loguru import logger

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.bind(logger_name=record.name).opt(exception=record.exc_info).log(level, record.getMessage())


def _record_patch(record: dict[str, Any]) -> None:
    """为每条日志补充稳定的上下文字段，避免结构化日志字段缺失。"""
    extra = record.setdefault("extra", {})
    extra.setdefault("service", "unknown")
    extra["request_id"] = request_id_var.get()
    extra["job_id"] = job_id_var.get()


def configure_logging(*, service_name: str, log_level: str = "INFO", serialize: bool = True) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=log_level.upper(),
        serialize=serialize,
        backtrace=False,
        diagnose=False,
        enqueue=True,
        format="{message}",
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logger.configure(
        extra={"service": service_name, "request_id": None, "job_id": None},
        patcher=_record_patch,
    )


def bind_request_context(*, request_id: str | None = None, job_id: str | None = None):
    values = {}
    if request_id is not None:
        request_id_var.set(request_id)
        values["request_id"] = request_id
    if job_id is not None:
        job_id_var.set(job_id)
        values["job_id"] = job_id
    return logger.bind(**values)


def clear_request_context() -> None:
    """清空请求上下文，避免长生命周期线程/协程复用导致上下文残留。"""
    request_id_var.set(None)
    job_id_var.set(None)
