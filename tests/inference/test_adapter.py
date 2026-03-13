"""verbose_json → TranscriptDocument 转换测试。"""

from __future__ import annotations

from minutes_core.profiles import JobProfile
from minutes_inference.engines.adapter import verbose_json_to_transcript


def test_verbose_json_converts_seconds_to_milliseconds() -> None:
    response = {
        "text": "你好世界",
        "language": "zh",
        "duration": 3.0,
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.5, "text": "你好", "x_speaker_id": "speaker_1", "x_confidence": 0.95},
            {"id": 1, "start": 1.5, "end": 3.0, "text": "世界", "x_speaker_id": "speaker_2", "x_confidence": 0.88},
        ],
        "x_speakers": [
            {"speaker_id": "speaker_1", "display_name": "Speaker 1", "segment_count": 1, "total_duration": 1.5},
            {"speaker_id": "speaker_2", "display_name": "Speaker 2", "segment_count": 1, "total_duration": 1.5},
        ],
    }

    doc = verbose_json_to_transcript(response, job_id="job-1", profile=JobProfile.CN_MEETING)

    assert doc.job_id == "job-1"
    assert doc.language == "zh"
    assert doc.full_text == "你好世界"
    assert doc.model_profile == JobProfile.CN_MEETING

    assert len(doc.segments) == 2
    assert doc.segments[0].start_ms == 0
    assert doc.segments[0].end_ms == 1500
    assert doc.segments[0].speaker_id == "speaker_1"
    assert doc.segments[0].confidence == 0.95
    assert doc.segments[1].start_ms == 1500
    assert doc.segments[1].end_ms == 3000

    assert len(doc.speakers) == 2
    assert doc.speakers[0].total_ms == 1500


def test_verbose_json_handles_empty_segments() -> None:
    response = {"text": "hello", "language": "en", "duration": 1.0}

    doc = verbose_json_to_transcript(response, job_id="job-2", profile=JobProfile.CN_MEETING)

    assert doc.full_text == "hello"
    assert doc.segments == []
    assert doc.speakers == []
    assert doc.paragraphs == ["hello"]


def test_verbose_json_empty_text_gives_no_paragraphs() -> None:
    response = {"text": "", "language": "en", "duration": 0.0}

    doc = verbose_json_to_transcript(response, job_id="job-3", profile=JobProfile.CN_MEETING)

    assert doc.paragraphs == []
