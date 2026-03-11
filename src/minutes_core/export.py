from __future__ import annotations

import json

from minutes_core.schemas import TranscriptDocument


def format_txt(document: TranscriptDocument) -> str:
    if document.full_text:
        return document.full_text
    return "\n".join(segment.text for segment in document.segments)


def _format_timestamp(milliseconds: int, *, vtt: bool = False) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def format_srt(document: TranscriptDocument) -> str:
    lines: list[str] = []
    for index, segment in enumerate(document.segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_format_timestamp(segment.start_ms)} --> {_format_timestamp(segment.end_ms)}",
                segment.text,
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_vtt(document: TranscriptDocument) -> str:
    lines = ["WEBVTT", ""]
    for segment in document.segments:
        lines.extend(
            [
                f"{_format_timestamp(segment.start_ms, vtt=True)} --> {_format_timestamp(segment.end_ms, vtt=True)}",
                segment.text,
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_json(document: TranscriptDocument) -> str:
    return json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)

