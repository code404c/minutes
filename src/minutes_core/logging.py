from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

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
    logger.configure(extra={"service": service_name, "request_id": None, "job_id": None})


def bind_request_context(*, request_id: str | None = None, job_id: str | None = None):
    values = {}
    if request_id is not None:
        request_id_var.set(request_id)
        values["request_id"] = request_id
    if job_id is not None:
        job_id_var.set(job_id)
        values["job_id"] = job_id
    return logger.bind(**values)

