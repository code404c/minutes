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
from minutes_core.storage import StorageManager
from minutes_gateway.dependencies import (
    get_db_session,
    get_event_bus,
    get_queue_dispatcher,
    get_storage_manager,
    verify_api_key,
)

router = APIRouter(prefix="/api/v1", tags=["jobs"], dependencies=[Depends(verify_api_key)])


def _parse_hotwords(raw_value: str | None) -> list[str]:
    if raw_value is None or not raw_value.strip():
        return []
    normalized = raw_value.replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _content_for_export(document: TranscriptDocument, export_format: str) -> tuple[str, str]:
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
    file: UploadFile = File(...),
    profile: str | None = Form(default=None),
    language: str | None = Form(default=None),
    hotwords: str | None = Form(default=None),
    session=Depends(get_db_session),
    storage_manager: StorageManager = Depends(get_storage_manager),
    queue_dispatcher: QueueDispatcher = Depends(get_queue_dispatcher),
) -> JobRead:
    job_id = str(uuid.uuid4())
    source_path, output_dir = storage_manager.save_upload(file, job_id=job_id)
    repository = JobRepository(session)
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
    queue_dispatcher.enqueue_prepare_job(detail.id)
    return repository.to_read(detail)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, session=Depends(get_db_session)) -> JobRead:
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository.to_read(detail)


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptDocument)
def get_transcript(job_id: str, session=Depends(get_db_session)) -> TranscriptDocument:
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if detail.result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcript is not ready yet.")
    return detail.result


@router.get("/jobs/{job_id}/export")
def export_transcript(job_id: str, format: str, session=Depends(get_db_session)) -> Response:
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
    repository = JobRepository(session)
    detail = repository.get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    async def _event_generator() -> AsyncIterator[dict[str, str]]:
        initial = JobEvent(
            event="snapshot",
            job_id=detail.id,
            status=detail.status,
            progress=detail.progress,
            stage=detail.status.value,
            payload={"error_code": detail.error_code} if detail.error_code else {},
        )
        yield {"event": "job", "data": initial.model_dump_json()}
        async for message in event_bus.subscribe(job_id):
            yield {"event": "job", "data": message}

    return EventSourceResponse(_event_generator())
