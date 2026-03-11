from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from minutes_core.constants import JobStatus
from minutes_core.export import format_srt, format_txt, format_vtt
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate, OpenAITranscriptionResponse
from minutes_core.storage import StorageManager
from minutes_core.queue import QueueDispatcher
from minutes_core.profiles import resolve_profile
from minutes_gateway.dependencies import (
    get_db_session,
    get_queue_dispatcher,
    get_settings,
    get_storage_manager,
    verify_api_key,
)

router = APIRouter(prefix="/v1/audio", tags=["openai-compatible"], dependencies=[Depends(verify_api_key)])

ResponseFormat = Literal["json", "text", "verbose_json", "srt", "vtt"]


async def _await_job_completion(
    repository: JobRepository,
    job_id: str,
    *,
    timeout_seconds: int,
) -> object:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        repository.session.expire_all()
        detail = repository.get_job(job_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job disappeared.")
        if detail.status == JobStatus.COMPLETED and detail.result is not None:
            return detail.result
        if detail.status == JobStatus.FAILED:
            if detail.error_code == "SYNC_DURATION_LIMIT_EXCEEDED":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail.error_message)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail.error_message or "Job failed.")
        await asyncio.sleep(0.2)
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Timed out waiting for synchronous transcription.",
    )


@router.post("/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    response_format: ResponseFormat = Form(default="json"),
    stream: bool = Form(default=False),
    hotwords: str | None = Form(default=None),
    session=Depends(get_db_session),
    storage_manager: StorageManager = Depends(get_storage_manager),
    queue_dispatcher: QueueDispatcher = Depends(get_queue_dispatcher),
    settings=Depends(get_settings),
) -> Response:
    if stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming is not supported on the synchronous OpenAI-compatible endpoint.",
        )

    job_id = str(uuid.uuid4())
    source_path, output_dir = storage_manager.save_upload(file, job_id=job_id)
    repository = JobRepository(session)
    detail = repository.create_job(
        JobCreate(
            job_id=job_id,
            source_filename=file.filename or "upload.bin",
            source_content_type=file.content_type,
            source_path=str(source_path),
            output_dir=str(output_dir),
            profile=resolve_profile(model),
            language=language,
            hotwords=[item.strip() for item in (hotwords or "").split(",") if item.strip()],
            sync_mode=True,
        )
    )
    queue_dispatcher.enqueue_prepare_job(detail.id)
    result = await _await_job_completion(repository, detail.id, timeout_seconds=settings.sync_wait_timeout_s)

    if response_format == "json":
        return JSONResponse(OpenAITranscriptionResponse(text=result.full_text).model_dump())
    if response_format == "text":
        return PlainTextResponse(format_txt(result))
    if response_format == "srt":
        return PlainTextResponse(format_srt(result), media_type="application/x-subrip")
    if response_format == "vtt":
        return PlainTextResponse(format_vtt(result), media_type="text/vtt")
    return JSONResponse(result.model_dump(mode="json"))
