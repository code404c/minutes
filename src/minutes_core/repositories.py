from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from minutes_core.constants import JobStatus
from minutes_core.models import JobRecord
from minutes_core.profiles import JobProfile, resolve_profile
from minutes_core.schemas import JobCreate, JobDetail, JobRead, TranscriptDocument


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(self, payload: JobCreate) -> JobDetail:
        now = datetime.now(UTC)
        record = JobRecord(
            id=payload.job_id or str(uuid.uuid4()),
            status=JobStatus.QUEUED.value,
            profile=resolve_profile(payload.profile).value,
            source_filename=payload.source_filename,
            source_content_type=payload.source_content_type,
            source_path=payload.source_path,
            output_dir=payload.output_dir,
            language=payload.language,
            hotwords_json=json.dumps(payload.hotwords, ensure_ascii=False),
            sync_mode=1 if payload.sync_mode else 0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._to_detail(record)

    def get_job(self, job_id: str) -> JobDetail | None:
        record = self.session.get(JobRecord, job_id)
        if record is None:
            return None
        return self._to_detail(record)

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: int | None = None,
        normalized_path: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        language: str | None = None,
    ) -> JobDetail:
        record = self.session.get(JobRecord, job_id)
        if record is None:
            raise KeyError(job_id)
        if status is not None:
            record.status = status.value
            if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                record.completed_at = datetime.now(UTC)
        if progress is not None:
            record.progress = progress
        if normalized_path is not None:
            record.normalized_path = normalized_path
        if duration_ms is not None:
            record.duration_ms = duration_ms
        if error_code is not None:
            record.error_code = error_code
        if error_message is not None:
            record.error_message = error_message
        if language is not None:
            record.language = language
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._to_detail(record)

    def save_result(self, job_id: str, document: TranscriptDocument) -> JobDetail:
        record = self.session.get(JobRecord, job_id)
        if record is None:
            raise KeyError(job_id)
        record.result_json = document.model_dump_json()
        record.progress = 100
        record.status = JobStatus.COMPLETED.value
        record.completed_at = datetime.now(UTC)
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._to_detail(record)

    @staticmethod
    def _to_detail(record: JobRecord) -> JobDetail:
        result = TranscriptDocument.model_validate_json(record.result_json) if record.result_json else None
        return JobDetail(
            id=record.id,
            status=JobStatus(record.status),
            profile=JobProfile(record.profile),
            source_filename=record.source_filename,
            source_content_type=record.source_content_type,
            source_path=record.source_path,
            output_dir=record.output_dir,
            duration_ms=record.duration_ms,
            language=record.language,
            hotwords=json.loads(record.hotwords_json),
            progress=record.progress,
            error_code=record.error_code,
            error_message=record.error_message,
            sync_mode=bool(record.sync_mode),
            normalized_path=record.normalized_path,
            result=result,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def to_read(detail: JobDetail) -> JobRead:
        return JobRead(**detail.model_dump(exclude={"normalized_path", "result"}))
