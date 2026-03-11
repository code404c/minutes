from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, nullable=False)
    profile: Mapped[str] = mapped_column(String(64), default=JobProfile.CN_MEETING.value, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_content_type: Mapped[str | None] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_path: Mapped[str | None] = mapped_column(Text)
    output_dir: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(32))
    hotwords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    sync_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "profile": self.profile,
            "source_filename": self.source_filename,
            "source_content_type": self.source_content_type,
            "source_path": self.source_path,
            "normalized_path": self.normalized_path,
            "output_dir": self.output_dir,
            "duration_ms": self.duration_ms,
            "language": self.language,
            "hotwords_json": self.hotwords_json,
            "progress": self.progress,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "sync_mode": bool(self.sync_mode),
            "result_json": self.result_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

