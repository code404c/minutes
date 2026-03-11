from __future__ import annotations

from typing import Protocol

import dramatiq
from dramatiq.brokers.redis import RedisBroker


class QueueDispatcher(Protocol):
    def enqueue_prepare_job(self, job_id: str) -> None: ...

    def enqueue_finalize_job(self, job_id: str) -> None: ...

    def enqueue_transcription_job(self, job_id: str) -> None: ...


def configure_broker(redis_url: str) -> RedisBroker:
    broker = RedisBroker(url=redis_url)
    dramatiq.set_broker(broker)
    return broker


class DramatiqQueueDispatcher:
    def enqueue_prepare_job(self, job_id: str) -> None:
        from minutes_orchestrator.actors import prepare_job_actor

        prepare_job_actor.send(job_id)

    def enqueue_finalize_job(self, job_id: str) -> None:
        from minutes_orchestrator.actors import finalize_job_actor

        finalize_job_actor.send(job_id)

    def enqueue_transcription_job(self, job_id: str) -> None:
        from minutes_inference.actors import transcribe_job_actor

        transcribe_job_actor.send(job_id)

