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
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, []),
            ("", []),
            ("   ", []),
        ],
        ids=["none", "empty-string", "whitespace-only"],
    )
    def test_empty_input_returns_empty_list(self, raw: str | None, expected: list[str]) -> None:
        assert _parse_hotwords(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("预算,风险,排期", ["预算", "风险", "排期"]),
            ("预算\n风险\n排期", ["预算", "风险", "排期"]),
            ("预算,风险\n排期", ["预算", "风险", "排期"]),
        ],
        ids=["comma-separated", "newline-separated", "mixed-separators"],
    )
    def test_separator_variants(self, raw: str, expected: list[str]) -> None:
        assert _parse_hotwords(raw) == expected

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
    @pytest.mark.parametrize(
        "fmt,expected_media_type,content_check",
        [
            ("txt", "text/plain; charset=utf-8", "你好，世界"),
            ("srt", "application/x-subrip", "00:00:00,000 --> 00:00:01,500"),
            ("vtt", "text/vtt; charset=utf-8", "00:00:00.000 --> 00:00:01.500"),
            ("json", "application/json", '"job_id"'),
        ],
        ids=["txt", "srt", "vtt", "json"],
    )
    def test_supported_format(
        self,
        sample_export_document: TranscriptDocument,
        fmt: str,
        expected_media_type: str,
        content_check: str,
    ) -> None:
        content, media_type = _content_for_export(sample_export_document, fmt)
        assert content_check in content
        assert media_type == expected_media_type

    def test_vtt_format_starts_with_webvtt(self, sample_export_document: TranscriptDocument) -> None:
        content, _ = _content_for_export(sample_export_document, "vtt")
        assert content.startswith("WEBVTT")

    def test_unsupported_format_raises_400(self, sample_export_document: TranscriptDocument) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _content_for_export(sample_export_document, "docx")
        assert exc_info.value.status_code == 400
        assert "docx" in str(exc_info.value.detail)
