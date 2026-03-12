"""jobs.py 中辅助函数 _parse_hotwords 和 _content_for_export 的单元测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from minutes_core.profiles import JobProfile
from minutes_core.schemas import Segment, TranscriptDocument
from minutes_gateway.routers.jobs import _content_for_export, _parse_hotwords

# ---------------------------------------------------------------------------
# _parse_hotwords 测试
# ---------------------------------------------------------------------------


class TestParseHotwords:
    def test_none_returns_empty_list(self) -> None:
        assert _parse_hotwords(None) == []

    def test_empty_string_returns_empty_list(self) -> None:
        assert _parse_hotwords("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert _parse_hotwords("   ") == []

    def test_comma_separated(self) -> None:
        assert _parse_hotwords("预算,风险,排期") == ["预算", "风险", "排期"]

    def test_newline_separated(self) -> None:
        assert _parse_hotwords("预算\n风险\n排期") == ["预算", "风险", "排期"]

    def test_mixed_separators(self) -> None:
        assert _parse_hotwords("预算,风险\n排期") == ["预算", "风险", "排期"]

    def test_strips_whitespace(self) -> None:
        assert _parse_hotwords(" 预算 , 风险 ") == ["预算", "风险"]

    def test_skips_empty_entries(self) -> None:
        assert _parse_hotwords("预算,,风险,") == ["预算", "风险"]

    def test_single_word(self) -> None:
        assert _parse_hotwords("OpenAI") == ["OpenAI"]


# ---------------------------------------------------------------------------
# _content_for_export 测试
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_export_document() -> TranscriptDocument:
    return TranscriptDocument(
        job_id="test-export",
        language="zh",
        full_text="你好，世界",
        segments=[
            Segment(start_ms=0, end_ms=1500, speaker_id="spk-1", text="你好，世界", confidence=0.98),
        ],
        paragraphs=["你好，世界"],
        speakers=[],
        model_profile=JobProfile.CN_MEETING,
    )


class TestContentForExport:
    def test_txt_format(self, sample_export_document: TranscriptDocument) -> None:
        content, media_type = _content_for_export(sample_export_document, "txt")
        assert "你好，世界" in content
        assert media_type == "text/plain; charset=utf-8"

    def test_srt_format(self, sample_export_document: TranscriptDocument) -> None:
        content, media_type = _content_for_export(sample_export_document, "srt")
        assert "00:00:00,000 --> 00:00:01,500" in content
        assert media_type == "application/x-subrip"

    def test_vtt_format(self, sample_export_document: TranscriptDocument) -> None:
        content, media_type = _content_for_export(sample_export_document, "vtt")
        assert content.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:01.500" in content
        assert media_type == "text/vtt; charset=utf-8"

    def test_json_format(self, sample_export_document: TranscriptDocument) -> None:
        content, media_type = _content_for_export(sample_export_document, "json")
        assert '"job_id"' in content
        assert media_type == "application/json"

    def test_unsupported_format_raises_400(self, sample_export_document: TranscriptDocument) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _content_for_export(sample_export_document, "docx")
        assert exc_info.value.status_code == 400
        assert "docx" in str(exc_info.value.detail)
