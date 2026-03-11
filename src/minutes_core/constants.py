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
