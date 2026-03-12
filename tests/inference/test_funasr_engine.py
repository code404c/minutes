"""FunASREngine._build_segments 和 _build_speakers 的单元测试。"""

from __future__ import annotations

from minutes_core.schemas import Segment
from minutes_inference.engines.funasr_engine import FunASREngine

# ---------------------------------------------------------------------------
# _build_segments 测试
# ---------------------------------------------------------------------------


class TestBuildSegments:
    """测试 _build_segments 静态方法的各种输入场景。"""

    def test_empty_sentence_info_returns_fallback_segment(self) -> None:
        """空 sentence_info 应返回包含 fallback_text 的单个分段。"""
        segments = FunASREngine._build_segments([], "整段文本", 5_000)

        assert len(segments) == 1
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 5_000
        assert segments[0].text == "整段文本"
        assert segments[0].speaker_id == "speaker_1"
        assert segments[0].confidence is None

    def test_empty_sentence_info_with_zero_duration_uses_minimum(self) -> None:
        """fallback_duration_ms 为 0 时，end_ms 应至少为 1000。"""
        segments = FunASREngine._build_segments([], "文本", 0)

        assert segments[0].end_ms == 1_000

    def test_empty_sentence_info_with_small_duration_uses_minimum(self) -> None:
        """fallback_duration_ms 小于 1000 时，end_ms 应为 1000。"""
        segments = FunASREngine._build_segments([], "文本", 500)

        assert segments[0].end_ms == 1_000

    def test_single_sentence_with_spk_field(self) -> None:
        """使用 'spk' 字段提供说话人信息。"""
        info = [{"start": 0, "end": 2000, "spk": "张三", "text": "你好", "confidence": 0.95}]
        segments = FunASREngine._build_segments(info, "", 2000)

        assert len(segments) == 1
        assert segments[0].speaker_id == "张三"
        assert segments[0].text == "你好"
        assert segments[0].confidence == 0.95
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 2000

    def test_single_sentence_with_speaker_field(self) -> None:
        """使用 'speaker' 字段提供说话人信息（第二优先级）。"""
        info = [{"start": 100, "end": 3000, "speaker": "speaker_A", "text": "测试"}]
        segments = FunASREngine._build_segments(info, "", 3000)

        assert segments[0].speaker_id == "speaker_A"

    def test_speaker_field_fallback_to_index(self) -> None:
        """无 spk/speaker 字段时，使用 speaker_{index} 作为默认值。"""
        info = [{"start": 0, "end": 1000, "text": "第一句"}, {"start": 1000, "end": 2000, "text": "第二句"}]
        segments = FunASREngine._build_segments(info, "", 2000)

        assert segments[0].speaker_id == "speaker_1"
        assert segments[1].speaker_id == "speaker_2"

    def test_spk_field_takes_priority_over_speaker(self) -> None:
        """spk 字段优先于 speaker 字段。"""
        info = [{"start": 0, "end": 1000, "spk": "优先", "speaker": "次要", "text": "内容"}]
        segments = FunASREngine._build_segments(info, "", 1000)

        assert segments[0].speaker_id == "优先"

    def test_multiple_sentences(self) -> None:
        """多个句子应正确解析为多个分段。"""
        info = [
            {"start": 0, "end": 1500, "spk": "spk1", "text": "第一句", "confidence": 0.9},
            {"start": 1500, "end": 3000, "spk": "spk2", "text": "第二句", "confidence": 0.85},
            {"start": 3000, "end": 4500, "spk": "spk1", "text": "第三句", "confidence": 0.92},
        ]
        segments = FunASREngine._build_segments(info, "", 4500)

        assert len(segments) == 3
        assert segments[0].text == "第一句"
        assert segments[1].speaker_id == "spk2"
        assert segments[2].confidence == 0.92

    def test_missing_start_defaults_to_zero(self) -> None:
        """缺少 start 字段时默认为 0。"""
        info = [{"end": 2000, "text": "内容"}]
        segments = FunASREngine._build_segments(info, "", 2000)

        assert segments[0].start_ms == 0

    def test_missing_end_defaults_to_start_plus_1000(self) -> None:
        """缺少 end 字段时默认为 start + 1000。"""
        info = [{"start": 500, "text": "内容"}]
        segments = FunASREngine._build_segments(info, "", 2000)

        assert segments[0].end_ms == 1500

    def test_text_is_stripped(self) -> None:
        """文本应被 strip 处理。"""
        info = [{"start": 0, "end": 1000, "text": "  前后有空格  "}]
        segments = FunASREngine._build_segments(info, "", 1000)

        assert segments[0].text == "前后有空格"

    def test_missing_text_defaults_to_empty(self) -> None:
        """缺少 text 字段时默认为空字符串。"""
        info = [{"start": 0, "end": 1000}]
        segments = FunASREngine._build_segments(info, "", 1000)

        assert segments[0].text == ""

    def test_no_confidence_defaults_to_none(self) -> None:
        """缺少 confidence 字段时默认为 None。"""
        info = [{"start": 0, "end": 1000, "text": "内容"}]
        segments = FunASREngine._build_segments(info, "", 1000)

        assert segments[0].confidence is None

    def test_speaker_id_is_stringified(self) -> None:
        """spk 字段为整数时应转为字符串。"""
        info = [{"start": 0, "end": 1000, "spk": 42, "text": "内容"}]
        segments = FunASREngine._build_segments(info, "", 1000)

        assert segments[0].speaker_id == "42"


# ---------------------------------------------------------------------------
# _build_speakers 测试
# ---------------------------------------------------------------------------


class TestBuildSpeakers:
    """测试 _build_speakers 静态方法。"""

    def test_empty_segments_returns_empty(self) -> None:
        """空分段列表应返回空说话人列表。"""
        speakers = FunASREngine._build_speakers([])

        assert speakers == []

    def test_segments_with_no_speaker_id_returns_empty(self) -> None:
        """所有分段 speaker_id 为 None 时应返回空列表。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id=None, text="匿名"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert speakers == []

    def test_single_speaker_statistics(self) -> None:
        """单个说话人的统计应正确计算。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id="spk1", text="第一句"),
            Segment(start_ms=1000, end_ms=3000, speaker_id="spk1", text="第二句"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert len(speakers) == 1
        assert speakers[0].speaker_id == "spk1"
        assert speakers[0].segment_count == 2
        assert speakers[0].total_ms == 3000  # (1000-0) + (3000-1000)

    def test_multiple_speakers_sorted_by_id(self) -> None:
        """多个说话人应按 speaker_id 排序返回。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id="spk_b", text="B说"),
            Segment(start_ms=1000, end_ms=2000, speaker_id="spk_a", text="A说"),
            Segment(start_ms=2000, end_ms=3500, speaker_id="spk_b", text="B又说"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert len(speakers) == 2
        assert speakers[0].speaker_id == "spk_a"
        assert speakers[0].segment_count == 1
        assert speakers[0].total_ms == 1000
        assert speakers[1].speaker_id == "spk_b"
        assert speakers[1].segment_count == 2
        assert speakers[1].total_ms == 2500

    def test_display_name_formatting(self) -> None:
        """display_name 应将下划线替换为空格，并使用 Title Case。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id="speaker_1", text="内容"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert speakers[0].display_name == "Speaker 1"

    def test_display_name_without_underscore(self) -> None:
        """没有下划线的 speaker_id 应直接 Title Case。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id="张三", text="内容"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert speakers[0].display_name == "张三"

    def test_mixed_none_and_named_speakers(self) -> None:
        """混合 None 和有名字的说话人时，应只统计有名字的。"""
        segments = [
            Segment(start_ms=0, end_ms=1000, speaker_id=None, text="匿名"),
            Segment(start_ms=1000, end_ms=2000, speaker_id="spk1", text="有名"),
            Segment(start_ms=2000, end_ms=3000, speaker_id=None, text="匿名2"),
            Segment(start_ms=3000, end_ms=4000, speaker_id="spk1", text="有名2"),
        ]
        speakers = FunASREngine._build_speakers(segments)

        assert len(speakers) == 1
        assert speakers[0].speaker_id == "spk1"
        assert speakers[0].segment_count == 2
        assert speakers[0].total_ms == 2000
