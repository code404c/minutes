from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from minutes_core.constants import JobStatus
from minutes_core.profiles import JobProfile


class Segment(BaseModel):
    """
    语音转写结果中的单个片段。
    """

    start_ms: int  # 片段开始时间（毫秒）
    end_ms: int  # 片段结束时间（毫秒）
    speaker_id: str | None = None  # 说话人标识符
    text: str  # 该片段的转写文本
    confidence: float | None = None  # 置信度评分
    emotion: str | None = None  # 情感分析结果
    event_tags: list[str] = Field(default_factory=list)  # 事件标签（如：笑声、掌声等）


class Speaker(BaseModel):
    """
    说话人统计信息。
    """

    speaker_id: str  # 说话人唯一标识
    display_name: str  # 显示名称
    segment_count: int  # 该说话人的片段总数
    total_ms: int  # 该说话人的总发言时长（毫秒）


class TranscriptDocument(BaseModel):
    """
    完整的转写文档结果。
    """

    job_id: str  # 任务 ID
    language: str  # 识别出的语言
    full_text: str  # 完整合并后的文本
    segments: list[Segment] = Field(default_factory=list)  # 片段列表
    paragraphs: list[str] = Field(default_factory=list)  # 分段后的文本列表
    speakers: list[Speaker] = Field(default_factory=list)  # 说话人列表
    model_profile: JobProfile  # 使用的任务配置方案


class JobCreate(BaseModel):
    """
    创建转写任务的请求模式。
    """

    job_id: str | None = None  # 可选的任务 ID
    source_filename: str  # 原始文件名
    source_content_type: str | None = None  # 内容类型（MIME type）
    source_path: str  # 原始文件存储路径
    output_dir: str  # 结果输出目录
    profile: JobProfile = JobProfile.CN_MEETING  # 任务配置方案（默认中文会议）
    language: str | None = None  # 指定语言
    hotwords: list[str] = Field(default_factory=list)  # 热词列表
    sync_mode: bool = False  # 是否以同步模式运行


class JobRead(BaseModel):
    """
    用于 API 响应的任务简要信息模式。
    """

    id: str
    status: JobStatus  # 任务当前状态
    profile: JobProfile  # 使用的任务配置方案
    source_filename: str  # 原始文件名
    source_content_type: str | None = None
    duration_ms: int | None = None  # 音频时长（毫秒）
    language: str | None = None
    hotwords: list[str] = Field(default_factory=list)
    progress: int = 0  # 处理进度（0-100）
    error_code: str | None = None  # 错误码
    error_message: str | None = None  # 错误详细信息
    sync_mode: bool = False
    created_at: datetime  # 创建时间
    updated_at: datetime  # 最后更新时间
    completed_at: datetime | None = None  # 完成时间


class JobDetail(JobRead):
    """
    用于 API 响应的任务详细信息模式，包含结果内容。
    """

    source_path: str
    output_dir: str
    normalized_path: str | None = None  # 标准化后的音频路径
    result: TranscriptDocument | None = None  # 转写结果文档


class JobEvent(BaseModel):
    """
    通过 Redis 发布/订阅发送的任务事件模式。
    """

    event: str  # 事件类型（如 'status_changed', 'progress_updated'）
    job_id: str  # 任务 ID
    status: JobStatus  # 任务状态
    progress: int  # 当前进度
    stage: str  # 当前处理阶段
    message: str | None = None  # 事件描述消息
    payload: dict[str, object] = Field(default_factory=dict)  # 额外数据负载


class OpenAITranscriptionResponse(BaseModel):
    """
    兼容 OpenAI Whisper API 格式的响应模式。
    """

    text: str
