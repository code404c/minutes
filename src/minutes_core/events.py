from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from minutes_core.constants import JOB_EVENT_CHANNEL_PREFIX
from minutes_core.schemas import JobEvent


class EventBus:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client = Redis.from_url(redis_url, decode_responses=True)

    @property
    def channel_prefix(self) -> str:
        return JOB_EVENT_CHANNEL_PREFIX

    def publish(self, event: JobEvent) -> None:
        self._client.publish(f"{self.channel_prefix}:{event.job_id}", event.model_dump_json())

    async def subscribe(self, job_id: str) -> AsyncIterator[str]:
        client = AsyncRedis.from_url(self.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"{self.channel_prefix}:{job_id}")
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    yield str(message["data"])
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(f"{self.channel_prefix}:{job_id}")
            await pubsub.close()
            await client.aclose()

    def close(self) -> None:
        self._client.close()
