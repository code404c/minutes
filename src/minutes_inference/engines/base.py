from __future__ import annotations

from pathlib import Path
from typing import Protocol

from minutes_core.schemas import JobDetail, TranscriptDocument


class InferenceEngine(Protocol):
    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument: ...

