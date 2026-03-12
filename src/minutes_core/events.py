from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from minutes_core.constants import JOB_EVENT_CHANNEL_PREFIX
from minutes_core.schemas import JobEvent


class EventBus:
    """
    事件总线，利用 Redis 的发布/订阅（Pub/Sub）机制。
    用于在系统内部组件间同步任务状态变化（例如：从计算节点通知网关）。
    """

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        # 同步 Redis 客户端，用于发布消息
        self._client = Redis.from_url(redis_url, decode_responses=True)

    @property
    def channel_prefix(self) -> str:
        """事件频道的前缀"""
        return JOB_EVENT_CHANNEL_PREFIX

    def publish(self, event: JobEvent) -> None:
        """
        发布一个任务事件到指定的 Redis 频道。
        频道名称格式为 "minutes:jobs:events:<job_id>"
        """
        self._client.publish(f"{self.channel_prefix}:{event.job_id}", event.model_dump_json())

    async def subscribe(self, job_id: str) -> AsyncIterator[str]:
        """
        异步订阅特定任务的事件频道。
        当有新事件发布时，通过异步迭代器产生消息内容。
        """
        # 使用异步 Redis 客户端进行长连接订阅
        client = AsyncRedis.from_url(self.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"{self.channel_prefix}:{job_id}")
        try:
            while True:
                # 每秒检查一次是否有新消息，避免无限阻塞
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    yield str(message["data"])
                # 防止 CPU 空转
                await asyncio.sleep(0.1)
        finally:
            # 确保在退出时正确释放资源
            await pubsub.unsubscribe(f"{self.channel_prefix}:{job_id}")
            await pubsub.close()
            await client.aclose()

    def close(self) -> None:
        """关闭同步 Redis 客户端"""
        self._client.close()
