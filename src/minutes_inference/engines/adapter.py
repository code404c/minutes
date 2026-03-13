"""将 OpenAI verbose_json 响应（含 x_ 扩展）转为 minutes 内部的 TranscriptDocument。"""

from __future__ import annotations

from typing import Any

from minutes_core.profiles import JobProfile
from minutes_core.schemas import Segment, Speaker, TranscriptDocument


def verbose_json_to_transcript(
    response: dict[str, Any],
    *,
    job_id: str,
    profile: JobProfile,
) -> TranscriptDocument:
    """将 OpenAI verbose_json 响应（含 x_ 扩展）转为 minutes 内部的 TranscriptDocument。

    负责：秒→毫秒转换、x_speaker_id 映射、x_speakers 构建等。
    """
    full_text = response.get("text", "")
    language = response.get("language", "")
    raw_segments = response.get("segments") or []
    raw_speakers = response.get("x_speakers") or []

    segments = [
        Segment(
            start_ms=int(round(seg.get("start", 0) * 1000)),
            end_ms=int(round(seg.get("end", 0) * 1000)),
            speaker_id=seg.get("x_speaker_id"),
            text=seg.get("text", ""),
            confidence=seg.get("x_confidence"),
        )
        for seg in raw_segments
    ]

    speakers = [
        Speaker(
            speaker_id=spk.get("speaker_id", ""),
            display_name=spk.get("display_name", ""),
            segment_count=spk.get("segment_count", 0),
            total_ms=int(round(spk.get("total_duration", 0) * 1000)),
        )
        for spk in raw_speakers
    ]

    return TranscriptDocument(
        job_id=job_id,
        language=language,
        full_text=full_text,
        segments=segments,
        paragraphs=[full_text] if full_text else [],
        speakers=speakers,
        model_profile=profile,
    )
