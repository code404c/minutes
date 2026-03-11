from __future__ import annotations

from pathlib import Path

from minutes_core.schemas import JobDetail, Segment, TranscriptDocument


class FakeInferenceEngine:
    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument:
        text = f"Fake transcript for {normalized_path.stem}"
        return TranscriptDocument(
            job_id=job.id,
            language=job.language or "zh",
            full_text=text,
            segments=[
                Segment(
                    start_ms=0,
                    end_ms=max(job.duration_ms or 2000, 2000),
                    speaker_id="speaker_1",
                    text=text,
                    confidence=0.99,
                )
            ],
            paragraphs=[text],
            speakers=[
                {
                    "speaker_id": "speaker_1",
                    "display_name": "Speaker 1",
                    "segment_count": 1,
                    "total_ms": max(job.duration_ms or 2000, 2000),
                }
            ],
            model_profile=job.profile,
        )
