from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sse_starlette import EventSourceResponse

from minutes_core.export import format_json, format_srt, format_txt, format_vtt
from minutes_core.profiles import resolve_profile
from minutes_core.queue import QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, JobEvent, JobRead, TranscriptDocument
from minutes_gateway.dependencies import (
    get_db_session,
    get_event_bus,
    get_queue_dispatcher,
    get_storage_manager,
    verify_api_key,
)

# 定义任务路由，添加认证依赖和标签
router = APIRouter(prefix="/api/v1", tags=["jobs"], dependencies=[Depends(verify_api_key)])


def _parse_hotwords(raw_value: str | None) -> list[str]:
    """
    解析热词字符串。支持逗号或换行符分隔。
    """
    if raw_value is None or not raw_value.strip():
        return []
    normalized = raw_value.replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _content_for_export(document: TranscriptDocument, export_format: str) -> tuple[str, str]:
    """
    根据请求的格式导出转录内容，返回内容和对应的 Media Type。
    """
    if export_format == "txt":
        return format_txt(document), "text/plain; charset=utf-8"
    if export_format == "srt":
        return format_srt(document), "application/x-subrip"
    if export_format == "vtt":
        return format_vtt(document), "text/vtt; charset=utf-8"
    if export_format == "json":
        return format_json(document), "application/json"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported export format: {export_format}")


@router.post("/jobs", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    file: UploadFile = File(...), # 待处理的音频文件
    profile: str | None = Form(default=None), # 模型配置（如 whisper, funasr）
    language: str | None = Form(default=None), # 指定语言
    hotwords: str | None = Form(default=None), # 识别热词
    session=Depends(get_db_session),
    storage_manager: StorageManager = Depends(get_storage_manager),
    queue_dispatcher: QueueDispatcher = Depends(get_queue_dispatcher),
) -> JobRead:
    """
    创建转录任务。
    
    1. 生成唯一的 job_id。
    2. 将上传的文件保存到持久化存储。
    3. 在数据库中创建任务记录。
    4. 将任务推送到 'prepare' 队列开始处理流水线。
    """
    job_id = str(uuid.uuid4())
    # 保存上传的文件并获取路径
    source_path, output_dir = storage_manager.save_upload(file, job_id=job_id)
    repository = JobRepository(session)
    # 数据库记录持久化
    detail = repository.create_job(
        JobCreate(
            job_id=job_id,
            source_filename=source_path.name,
            source_content_type=file.content_type,
            source_path=str(source_path),
            output_dir=str(output_dir),
            profile=resolve_profile(profile),
            language=language,
            hotwords=_parse_hotwords(hotwords),
        )
    )
    session.commit()
    # 触发异步处理流水线
    queue_dispatcher.enqueue_prepare_job(detail.id)
    return repository.to_read(detail)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, session=Depends(get_db_session)) -> JobRead:
    """获取任务的当前状态和元数据。"""
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository.to_read(detail)


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptDocument)
def get_transcript(job_id: str, session=Depends(get_db_session)) -> TranscriptDocument:
    """获取任务的转录结果 JSON。"""
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if detail.result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcript is not ready yet.")
    return detail.result


@router.get("/jobs/{job_id}/export")
def export_transcript(job_id: str, format: str, session=Depends(get_db_session)) -> Response:
    """以特定格式（txt, srt, vtt）导出转录文本。"""
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if detail.result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcript is not ready yet.")
    content, media_type = _content_for_export(detail.result, format)
    return Response(content=content, media_type=media_type)


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str, session=Depends(get_db_session), event_bus=Depends(get_event_bus)
) -> EventSourceResponse:
    """
    通过 Server-Sent Events (SSE) 实时订阅任务进度。
    
    该接口会先发送当前状态的快照，然后持续推送后续的进度更新事件。
    """
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    async def _event_generator() -> AsyncIterator[dict[str, str]]:
        # 发送初始快照
        initial = JobEvent(
            event="snapshot",
            job_id=detail.id,
            status=detail.status,
            progress=detail.progress,
            stage=detail.status.value,
            payload={"error_code": detail.error_code} if detail.error_code else {},
        )
        yield {"event": "job", "data": initial.model_dump_json()}
        # 订阅后续 Redis 事件
        async for message in event_bus.subscribe(job_id):
            yield {"event": "job", "data": message}

    return EventSourceResponse(_event_generator())
