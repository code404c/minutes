from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile


class Segment(BaseModel):
    start_ms: int
    end_ms: int
    speaker_id: str | None = None
    text: str
    confidence: float | None = None
    emotion: str | None = None
    event_tags: list[str] = Field(default_factory=list)


class Speaker(BaseModel):
    speaker_id: str
    display_name: str
    segment_count: int
    total_ms: int


class TranscriptDocument(BaseModel):
    job_id: str
    language: str
    full_text: str
    segments: list[Segment] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    speakers: list[Speaker] = Field(default_factory=list)
    model_profile: JobProfile


class JobCreate(BaseModel):
    job_id: str | None = None
    source_filename: str
    source_content_type: str | None = None
    source_path: str
    output_dir: str
    profile: JobProfile = JobProfile.CN_MEETING
    language: str | None = None
    hotwords: list[str] = Field(default_factory=list)
    sync_mode: bool = False


class JobRead(BaseModel):
    id: str
    status: JobStatus
    profile: JobProfile
    source_filename: str
    source_content_type: str | None = None
    duration_ms: int | None = None
    language: str | None = None
    hotwords: list[str] = Field(default_factory=list)
    progress: int = 0
    error_code: str | None = None
    error_message: str | None = None
    sync_mode: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class JobDetail(JobRead):
    source_path: str
    output_dir: str
    normalized_path: str | None = None
    result: TranscriptDocument | None = None


class JobEvent(BaseModel):
    event: str
    job_id: str
    status: JobStatus
    progress: int
    stage: str
    message: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class OpenAITranscriptionResponse(BaseModel):
    text: str
