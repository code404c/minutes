from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from loguru import logger

from minutes_core.constants import JobStatus
from minutes_core.export import format_srt, format_txt, format_vtt
from minutes_core.profiles import resolve_profile
from minutes_core.queue import QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, OpenAITranscriptionResponse
from minutes_core.storage import StorageManager
from minutes_gateway.dependencies import (
    get_db_session,
    get_queue_dispatcher,
    get_settings,
    get_storage_manager,
    verify_api_key,
)
from minutes_gateway.routers.jobs import _parse_hotwords

# 定义 OpenAI 兼容的音频转录路由
router = APIRouter(prefix="/v1/audio", tags=["openai-compatible"], dependencies=[Depends(verify_api_key)])

ResponseFormat = Literal["json", "text", "verbose_json", "srt", "vtt"]


async def _await_job_completion(
    repository: JobRepository,
    job_id: str,
    *,
    timeout_seconds: int,
) -> object:
    """
    内部辅助方法：轮询数据库以等待任务完成（用于同步 API）。

    Args:
        repository: 任务仓库。
        job_id: 任务 ID。
        timeout_seconds: 最大等待时间（秒）。
    """
    _POLL_INTERVAL = 0.2
    # 最大轮询次数，防止因时钟异常导致无限循环
    max_iterations = int(timeout_seconds / _POLL_INTERVAL) + 1
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    for _iteration in range(max_iterations):
        if asyncio.get_running_loop().time() >= deadline:
            break

        # 强制刷新 SQLAlchemy 缓存，获取最新数据库状态
        repository.session.expire_all()
        detail = repository.get_job(job_id)
        if detail is None:
            logger.warning("Job {} disappeared during polling.", job_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job disappeared.")

        # 任务成功完成
        if detail.status == JobStatus.COMPLETED and detail.result is not None:
            return detail.result

        # 任务失败处理
        if detail.status == JobStatus.FAILED:
            if detail.error_code == "SYNC_DURATION_LIMIT_EXCEEDED":
                logger.warning("Job {} exceeded sync duration limit: {}", job_id, detail.error_message)
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail.error_message)
            logger.warning("Job {} failed: {}", job_id, detail.error_message or "unknown reason")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail.error_message or "Job failed."
            )

        # 稍作等待后继续轮询
        await asyncio.sleep(_POLL_INTERVAL)

    logger.warning("Job {} polling timed out after {}s.", job_id, timeout_seconds)
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Timed out waiting for synchronous transcription.",
    )


@router.post("/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),  # 对应 Profile
    language: str | None = Form(default=None),
    response_format: ResponseFormat = Form(default="json"),
    stream: bool = Form(default=False),
    hotwords: str | None = Form(default=None),
    session=Depends(get_db_session),
    storage_manager: StorageManager = Depends(get_storage_manager),
    queue_dispatcher: QueueDispatcher = Depends(get_queue_dispatcher),
    settings=Depends(get_settings),
) -> Response:
    """
    OpenAI 兼容的转录接口 (POST /v1/audio/transcriptions)。

    该接口是同步的：它会接收文件，启动后台任务，然后阻塞连接直到任务完成或超时。
    """
    if stream:
        logger.warning("Streaming requested on synchronous OpenAI endpoint.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming is not supported on the synchronous OpenAI-compatible endpoint.",
        )

    job_id = str(uuid.uuid4())
    # 1. 保存文件
    source_path, output_dir = storage_manager.save_upload(file, job_id=job_id)
    repository = JobRepository(session)
    # 2. 创建任务记录（标记为 sync_mode）
    detail = repository.create_job(
        JobCreate(
            job_id=job_id,
            source_filename=source_path.name,
            source_content_type=file.content_type,
            source_path=str(source_path),
            output_dir=str(output_dir),
            profile=resolve_profile(model),
            language=language,
            hotwords=_parse_hotwords(hotwords),
            sync_mode=True,
        )
    )
    session.commit()
    # 3. 触发异步处理
    queue_dispatcher.enqueue_prepare_job(detail.id)

    # 4. 同步等待结果
    result = await _await_job_completion(repository, detail.id, timeout_seconds=settings.sync_wait_timeout_s)

    # 5. 根据请求的 response_format 返回不同格式的结果
    if response_format == "json":
        return JSONResponse(OpenAITranscriptionResponse(text=result.full_text).model_dump())
    if response_format == "text":
        return PlainTextResponse(format_txt(result))
    if response_format == "srt":
        return PlainTextResponse(format_srt(result), media_type="application/x-subrip")
    if response_format == "vtt":
        return PlainTextResponse(format_vtt(result), media_type="text/vtt")
    # 默认返回 verbose_json
    return JSONResponse(result.model_dump(mode="json"))
