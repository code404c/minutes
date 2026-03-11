from __future__ import annotations

import dramatiq

from minutes_core.config import get_settings
from minutes_core.queue import configure_broker
from minutes_orchestrator.services import OrchestratorService

settings = get_settings()
configure_broker(settings.redis_url)


@dramatiq.actor(queue_name="orchestrator")
def prepare_job_actor(job_id: str) -> None:
    OrchestratorService(settings=settings).prepare_job(job_id)


@dramatiq.actor(queue_name="orchestrator")
def finalize_job_actor(job_id: str) -> None:
    OrchestratorService(settings=settings).finalize_job(job_id)

