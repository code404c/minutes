from __future__ import annotations

import threading

import dramatiq
from loguru import logger

from minutes_core.config import get_settings
from minutes_core.logging import bind_request_context, configure_logging
from minutes_core.queue import configure_broker
from minutes_inference.service import InferenceService

# 获取全局配置并配置 Dramatiq 代理（Redis）
settings = get_settings()
configure_broker(settings.redis_url)
# 配置结构化日志（注册 _record_patch，使 job_id 自动注入日志）
configure_logging(service_name="inference", log_level=settings.log_level, serialize=settings.log_json)

# 定义任务重试和超时策略
MAX_RETRIES = 2
TIME_LIMIT_MS = 1_800_000  # 单次任务时间限制：30分钟
MAX_AGE_MS = 3_600_000  # 任务最大有效期：1小时

# 使用线程锁确保推理服务的单例初始化（对于加载大型模型至关重要）
_service: InferenceService | None = None
_service_lock = threading.Lock()


def get_inference_service() -> InferenceService:
    """
    获取推理服务的单例。

    在 Dramatiq Worker 进程内，该方法确保 InferenceService 只被初始化一次，
    从而避免重复加载大型 AI 模型。
    """
    global _service
    with _service_lock:
        if _service is None:
            _service = InferenceService(settings=settings)
        return _service


def _extract_retry_payload(
    message_data: dict[str, object], retry_data: dict[str, int]
) -> tuple[str | None, int, int | None]:
    """
    从 Dramatiq 的重试消息中提取任务 ID 和重试次数。
    """
    args = message_data.get("args")
    job_id = args[0] if isinstance(args, (list, tuple)) and args and isinstance(args[0], str) else None
    retries = retry_data.get("retries", 0)
    max_retries = retry_data.get("max_retries")
    return job_id, retries, max_retries


@dramatiq.actor(
    queue_name="inference",
    max_retries=MAX_RETRIES,
    time_limit=TIME_LIMIT_MS,
    max_age=MAX_AGE_MS,
    on_retry_exhausted="handle_inference_retry_exhausted",
)
def transcribe_job_actor(job_id: str) -> None:
    """
    执行转录任务的 Dramatiq Actor。

    该 Actor 监听 'inference' 队列。当接收到 job_id 时，它会调用推理服务进行转录。
    如果执行失败，Dramatiq 会根据 max_retries 进行自动重试。
    """
    bind_request_context(job_id=job_id)
    get_inference_service().transcribe_job(job_id)


@dramatiq.actor(queue_name="inference", max_retries=0, time_limit=TIME_LIMIT_MS, max_age=MAX_AGE_MS)
def handle_inference_retry_exhausted(message_data: dict[str, object], retry_data: dict[str, int]) -> None:
    """
    当任务重试次数耗尽时的错误处理 Actor。

    它会将任务状态更新为 FAILED，并记录详细的重试失败信息。
    """
    job_id, retries, max_retries = _extract_retry_payload(message_data, retry_data)
    if job_id is not None:
        bind_request_context(job_id=job_id)
    if job_id is None:
        logger.warning("Retry exhausted but failed to extract job_id from inference message payload.")
        return

    logger.warning(
        "Retry exhausted for inference actor: job_id={}, retries={}, max_retries={}",
        job_id,
        retries,
        max_retries,
    )
    get_inference_service().mark_retry_exhausted(job_id, retries=retries, max_retries=max_retries)
