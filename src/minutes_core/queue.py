from __future__ import annotations

from typing import Protocol

import dramatiq
from dramatiq.brokers.redis import RedisBroker


class QueueDispatcher(Protocol):
    """
    任务分发器的协议定义。
    规定了各个处理阶段的入队操作。
    """
    def enqueue_prepare_job(self, job_id: str) -> None:
        """将音频预处理任务入队"""
        ...

    def enqueue_finalize_job(self, job_id: str) -> None:
        """将转写后处理（总结、格式化等）任务入队"""
        ...

    def enqueue_transcription_job(self, job_id: str) -> None:
        """将语音转写推理任务入队"""
        ...


def configure_broker(redis_url: str) -> RedisBroker:
    """
    配置 Dramatiq 使用 Redis 作为消息代理。
    """
    broker = RedisBroker(url=redis_url)
    dramatiq.set_broker(broker)
    return broker


class DramatiqQueueDispatcher:
    """
    基于 Dramatiq 的任务分发器实现。
    负责将具体的任务发送到对应的 Actor 队列中。
    """
    def enqueue_prepare_job(self, job_id: str) -> None:
        """发送预处理请求"""
        from minutes_orchestrator.actors import prepare_job_actor

        prepare_job_actor.send(job_id)

    def enqueue_finalize_job(self, job_id: str) -> None:
        """发送后处理请求"""
        from minutes_orchestrator.actors import finalize_job_actor

        finalize_job_actor.send(job_id)

    def enqueue_transcription_job(self, job_id: str) -> None:
        """发送语音转写请求"""
        from minutes_inference.actors import transcribe_job_actor

        transcribe_job_actor.send(job_id)
