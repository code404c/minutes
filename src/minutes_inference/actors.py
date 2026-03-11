from __future__ import annotations

import dramatiq

from minutes_core.config import get_settings
from minutes_core.queue import configure_broker
from minutes_inference.service import InferenceService

settings = get_settings()
configure_broker(settings.redis_url)


@dramatiq.actor(queue_name="inference")
def transcribe_job_actor(job_id: str) -> None:
    InferenceService(settings=settings).transcribe_job(job_id)

