from __future__ import annotations

import json

from minutes_core.export import format_json, format_srt, format_txt, format_vtt
from minutes_core.schemas import TranscriptDocument


def test_format_txt_exports_full_text(sample_transcript_document: TranscriptDocument) -> None:
    exported = format_txt(sample_transcript_document)

    assert exported == "你好，世界\n这是第二句。"


def test_format_srt_exports_segment_cues(sample_transcript_document: TranscriptDocument) -> None:
    exported = format_srt(sample_transcript_document)

    assert exported == (
        "1\n"
        "00:00:00,000 --> 00:00:01,500\n"
        "你好，世界\n\n"
        "2\n"
        "00:00:01,500 --> 00:00:03,200\n"
        "这是第二句。"
    )


def test_format_vtt_exports_webvtt_document(sample_transcript_document: TranscriptDocument) -> None:
    exported = format_vtt(sample_transcript_document)

    assert exported == (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:01.500\n"
        "你好，世界\n\n"
        "00:00:01.500 --> 00:00:03.200\n"
        "这是第二句。"
    )


def test_format_json_serializes_transcript_document(
    sample_transcript_document: TranscriptDocument,
) -> None:
    exported = format_json(sample_transcript_document)
    payload = json.loads(exported)

    assert payload["job_id"] == "job-123"
    assert payload["language"] == "zh"
    assert payload["full_text"] == "你好，世界\n这是第二句。"
    assert payload["model_profile"] == "cn_meeting"
    assert payload["segments"][0]["start_ms"] == 0
    assert payload["segments"][1]["end_ms"] == 3200
    assert "你好，世界" in exported
