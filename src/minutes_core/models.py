from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile


class Base(DeclarativeBase):
    """
    SQLAlchemy ORM 声明式基类。
    """
    pass


class JobRecord(Base):
    """
    转写任务记录表（jobs 表）。
    存储任务的所有元数据、配置、当前状态、进度以及最终生成的转写结果。
    """
    __tablename__ = "jobs"
    __table_args__ = (
        # 对状态和创建时间建立索引，加速任务查询
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # 任务唯一 ID
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, nullable=False)  # 当前状态
    profile: Mapped[str] = mapped_column(String(64), default=JobProfile.CN_MEETING.value, nullable=False)  # 配置方案
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 上传时的原始文件名
    source_content_type: Mapped[str | None] = mapped_column(String(255))      # 文件的 MIME 类型
    source_path: Mapped[str] = mapped_column(Text, nullable=False)           # 存储在文件系统中的原始路径
    normalized_path: Mapped[str | None] = mapped_column(Text)                # 转换/归一化后的音频路径
    output_dir: Mapped[str] = mapped_column(Text, nullable=False)            # 结果输出目录
    duration_ms: Mapped[int | None] = mapped_column(Integer)                 # 音频总长度（毫秒）
    language: Mapped[str | None] = mapped_column(String(32))                 # 转写目标语言
    hotwords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # 任务热词（JSON 数组）
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 进度百分比 (0-100)
    error_code: Mapped[str | None] = mapped_column(String(128))              # 失败时的错误代码
    error_message: Mapped[str | None] = mapped_column(Text)                  # 失败时的详细消息
    sync_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False) # 标记是否为同步等待模式
    result_json: Mapped[str | None] = mapped_column(Text)                    # 转写结果 (JSON 格式的 TranscriptDocument)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False) # 任务创建时间
    updated_at: Mapped[datetime] = mapped_column(                             # 任务最后更新时间
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)) # 任务完成时间

    def as_dict(self) -> dict[str, Any]:
        """
        将数据库记录转换为字典，方便后续处理或序列化。
        """
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
