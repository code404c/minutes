from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


SYNC_TRANSCRIPTION_MAX_DURATION_MS = 15 * 60 * 1000
DEFAULT_SYNC_WAIT_TIMEOUT_S = 60
NORMALIZED_SAMPLE_RATE = 16_000
NORMALIZED_CHANNELS = 1
JOB_EVENT_CHANNEL_PREFIX = "minutes:jobs"
UPLOADS_DIRNAME = "uploads"
ARTIFACTS_DIRNAME = "artifacts"

# ── Pipeline 各阶段的 NOOP 状态集 ──────────────────────────
# 当任务处于这些状态时，对应阶段应跳过处理（避免重复执行）。

# 预处理阶段：已经进入转写或更后面的状态时跳过
PREPARE_NOOP_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.TRANSCRIBING,
        JobStatus.POSTPROCESSING,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
)

# 转写阶段：尚未预处理完成或已经后处理/完成时跳过
TRANSCRIBE_NOOP_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.POSTPROCESSING,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
)

# 收尾阶段：尚未开始转写或已经终态时跳过
FINALIZE_NOOP_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.PREPROCESSING,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
)
