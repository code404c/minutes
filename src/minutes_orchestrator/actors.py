from __future__ import annotations

import threading

import dramatiq

from minutes_core.config import get_settings
from minutes_core.queue import configure_broker
from minutes_orchestrator.services import OrchestratorService

settings = get_settings()
configure_broker(settings.redis_url)

MAX_RETRIES = 2
TIME_LIMIT_MS = 1_800_000
MAX_AGE_MS = 3_600_000

_service: OrchestratorService | None = None
_service_lock = threading.Lock()


def get_orchestrator_service() -> OrchestratorService:
    global _service
    with _service_lock:
        if _service is None:
            _service = OrchestratorService(settings=settings)
        return _service


def _extract_retry_payload(
    message_data: dict[str, object], retry_data: dict[str, int]
) -> tuple[str | None, int, int | None]:
    args = message_data.get("args")
    job_id = args[0] if isinstance(args, (list, tuple)) and args and isinstance(args[0], str) else None
    retries = retry_data.get("retries", 0)
    max_retries = retry_data.get("max_retries")
    return job_id, retries, max_retries


@dramatiq.actor(
    queue_name="orchestrator",
    max_retries=MAX_RETRIES,
    time_limit=TIME_LIMIT_MS,
    max_age=MAX_AGE_MS,
    on_retry_exhausted="handle_orchestrator_retry_exhausted",
)
def prepare_job_actor(job_id: str) -> None:
    get_orchestrator_service().prepare_job(job_id)


@dramatiq.actor(
    queue_name="orchestrator",
    max_retries=MAX_RETRIES,
    time_limit=TIME_LIMIT_MS,
    max_age=MAX_AGE_MS,
    on_retry_exhausted="handle_orchestrator_retry_exhausted",
)
def finalize_job_actor(job_id: str) -> None:
    get_orchestrator_service().finalize_job(job_id)


@dramatiq.actor(queue_name="orchestrator", max_retries=0, time_limit=TIME_LIMIT_MS, max_age=MAX_AGE_MS)
def handle_orchestrator_retry_exhausted(message_data: dict[str, object], retry_data: dict[str, int]) -> None:
    job_id, retries, max_retries = _extract_retry_payload(message_data, retry_data)
    actor_name = message_data.get("actor_name")
    if job_id is None or not isinstance(actor_name, str):
        return

    if actor_name == prepare_job_actor.actor_name:
        stage = "prepare"
    elif actor_name == finalize_job_actor.actor_name:
        stage = "finalize"
    else:
        return

    get_orchestrator_service().mark_retry_exhausted(
        job_id,
        stage=stage,
        retries=retries,
        max_retries=max_retries,
    )
