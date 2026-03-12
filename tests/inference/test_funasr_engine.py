"""FunASREngine 单元测试：静态方法 + transcribe + 模型加载 + 路径解析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from minutes_core.config import Settings
from minutes_core.profiles import JobProfile, get_profile_spec
from minutes_core.schemas import Segment
from minutes_inference.engines.funasr_engine import FunASREngine, FunASRUnavailableError
from minutes_inference.model_pool import TTLModelPool

from .conftest import make_job_detail

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


# ---------------------------------------------------------------------------
# transcribe() 测试
# ---------------------------------------------------------------------------


class TestTranscribe:
    """测试 transcribe 方法的编排逻辑（mock 掉模型加载）。"""

    @staticmethod
    def _make_engine(settings: Settings) -> tuple[FunASREngine, MagicMock]:
        """创建 engine 和可控的 fake model。"""
        pool: TTLModelPool[Any] = TTLModelPool(ttl_seconds=600)
        engine = FunASREngine(settings=settings, model_pool=pool)
        fake_model = MagicMock()
        return engine, fake_model

    @staticmethod
    def _patch_model_loading(monkeypatch, engine: FunASREngine, fake_model: MagicMock) -> None:
        monkeypatch.setattr(engine, "_get_or_load_model", lambda _key: fake_model)

    def test_transcribe_returns_complete_document(self, inference_settings, monkeypatch) -> None:
        """返回的 TranscriptDocument 包含正确的 job_id、language、full_text、segments、speakers。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [
            {
                "text": "你好世界",
                "sentence_info": [
                    {"start": 0, "end": 2000, "spk": "spk1", "text": "你好世界", "confidence": 0.95},
                ],
            }
        ]

        job = make_job_detail(job_id="j1", language="zh")
        doc = engine.transcribe(job, Path("/fake/audio.wav"))

        assert doc.job_id == "j1"
        assert doc.language == "zh"
        assert doc.full_text == "你好世界"
        assert len(doc.segments) == 1
        assert doc.segments[0].speaker_id == "spk1"
        assert len(doc.speakers) == 1

    def test_transcribe_with_hotwords_passes_hotword_kwarg(self, inference_settings, monkeypatch) -> None:
        """有 hotwords 且 profile 支持时，generate 应包含 hotword 参数。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "预算 风险", "sentence_info": []}]

        job = make_job_detail(hotwords=["预算", "风险"], profile=JobProfile.CN_MEETING)
        engine.transcribe(job, Path("/fake/audio.wav"))

        call_kwargs = model.generate.call_args[1]
        assert call_kwargs["hotword"] == "预算 风险"

    def test_transcribe_without_hotwords_skips_kwarg(self, inference_settings, monkeypatch) -> None:
        """空 hotwords 时 generate 调用不含 hotword 参数。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "文本", "sentence_info": []}]

        job = make_job_detail(hotwords=[])
        engine.transcribe(job, Path("/fake/audio.wav"))

        call_kwargs = model.generate.call_args[1]
        assert "hotword" not in call_kwargs

    def test_transcribe_hotwords_disabled_profile(self, inference_settings, monkeypatch) -> None:
        """supports_hotwords=False 时即使有 hotwords 也不传。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "文本", "sentence_info": []}]

        job = make_job_detail(hotwords=["词1"], profile=JobProfile.MULTILINGUAL_RICH)
        engine.transcribe(job, Path("/fake/audio.wav"))

        call_kwargs = model.generate.call_args[1]
        assert "hotword" not in call_kwargs

    def test_transcribe_empty_results_raises(self, inference_settings, monkeypatch) -> None:
        """model.generate 返回空列表时应抛出 RuntimeError。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = []

        job = make_job_detail()
        with pytest.raises(RuntimeError, match="no transcription results"):
            engine.transcribe(job, Path("/fake/audio.wav"))

    def test_transcribe_no_sentence_info_uses_fallback(self, inference_settings, monkeypatch) -> None:
        """结果无 sentence_info 时使用单 segment fallback。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "整段内容"}]

        job = make_job_detail(duration_ms=3000)
        doc = engine.transcribe(job, Path("/fake/audio.wav"))

        assert len(doc.segments) == 1
        assert doc.segments[0].text == "整段内容"
        assert doc.segments[0].end_ms == 3000

    def test_transcribe_uses_job_language(self, inference_settings, monkeypatch) -> None:
        """job.language 应传递给 generate。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "hello", "sentence_info": []}]

        job = make_job_detail(language="en")
        engine.transcribe(job, Path("/fake/audio.wav"))

        call_kwargs = model.generate.call_args[1]
        assert call_kwargs["language"] == "en"

    def test_transcribe_falls_back_to_profile_language(self, inference_settings, monkeypatch) -> None:
        """job.language 为 None 时使用 profile.default_language。"""
        engine, model = self._make_engine(inference_settings)
        self._patch_model_loading(monkeypatch, engine, model)
        model.generate.return_value = [{"text": "文本", "sentence_info": []}]

        job = make_job_detail(language=None, profile=JobProfile.CN_MEETING)
        doc = engine.transcribe(job, Path("/fake/audio.wav"))

        call_kwargs = model.generate.call_args[1]
        profile = get_profile_spec(JobProfile.CN_MEETING)
        assert call_kwargs["language"] == profile.default_language
        assert doc.language == profile.default_language


# ---------------------------------------------------------------------------
# _resolve_model_path() 测试
# ---------------------------------------------------------------------------


class TestResolveModelPath:
    """测试模型路径解析的优先级逻辑。"""

    def test_resolve_direct_path(self, inference_settings: Settings) -> None:
        """cache/model_id/ 存在时返回直接路径。"""
        engine = FunASREngine(settings=inference_settings, model_pool=TTLModelPool(ttl_seconds=60))
        cache = inference_settings.model_cache_dir
        direct = cache / "org/model_name"
        direct.mkdir(parents=True)

        result = engine._resolve_model_path("org/model_name")
        assert result == str(direct)

    def test_resolve_models_prefix(self, inference_settings: Settings) -> None:
        """仅 cache/models/model_id/ 存在时返回 models/ 路径。"""
        engine = FunASREngine(settings=inference_settings, model_pool=TTLModelPool(ttl_seconds=60))
        cache = inference_settings.model_cache_dir
        models_path = cache / "models" / "org/model_name"
        models_path.mkdir(parents=True)

        result = engine._resolve_model_path("org/model_name")
        assert result == str(models_path)

    def test_resolve_hub_prefix(self, inference_settings: Settings) -> None:
        """仅 cache/hub/model_id/ 存在时返回 hub/ 路径。"""
        engine = FunASREngine(settings=inference_settings, model_pool=TTLModelPool(ttl_seconds=60))
        cache = inference_settings.model_cache_dir
        hub_path = cache / "hub" / "org/model_name"
        hub_path.mkdir(parents=True)

        result = engine._resolve_model_path("org/model_name")
        assert result == str(hub_path)

    def test_resolve_priority_order(self, inference_settings: Settings) -> None:
        """三个目录都存在时直接路径优先。"""
        engine = FunASREngine(settings=inference_settings, model_pool=TTLModelPool(ttl_seconds=60))
        cache = inference_settings.model_cache_dir
        for prefix in ("", "models/", "hub/"):
            (cache / prefix / "org/model_name").mkdir(parents=True, exist_ok=True)

        result = engine._resolve_model_path("org/model_name")
        assert result == str(cache / "org/model_name")

    def test_resolve_returns_model_id_when_not_cached(self, inference_settings: Settings) -> None:
        """无本地缓存时返回原始 model_id。"""
        engine = FunASREngine(settings=inference_settings, model_pool=TTLModelPool(ttl_seconds=60))
        result = engine._resolve_model_path("nonexistent/model")
        assert result == "nonexistent/model"


# ---------------------------------------------------------------------------
# _get_or_load_model() 测试
# ---------------------------------------------------------------------------


class TestGetOrLoadModel:
    """测试模型池集成和加载逻辑。"""

    def test_delegates_to_model_pool(self, inference_settings: Settings) -> None:
        """应调用 model_pool.get_or_create(cache_key, loader)。"""
        pool = MagicMock(spec=TTLModelPool)
        sentinel = object()
        pool.get_or_create.return_value = sentinel

        engine = FunASREngine(settings=inference_settings, model_pool=pool)
        result = engine._get_or_load_model("cn_meeting")

        pool.get_or_create.assert_called_once()
        assert pool.get_or_create.call_args[0][0] == "cn_meeting"
        assert result is sentinel

    def test_loader_configures_automodel_correctly(self, inference_settings: Settings, monkeypatch) -> None:
        """loader 函数使用正确的 model_kwargs（asr_model, vad_model, device 等）。"""
        pool: TTLModelPool[Any] = TTLModelPool(ttl_seconds=600)
        engine = FunASREngine(settings=inference_settings, model_pool=pool)

        captured_kwargs: dict[str, Any] = {}
        fake_auto_model_cls = MagicMock()
        fake_auto_model_cls.side_effect = lambda **kw: captured_kwargs.update(kw) or MagicMock()

        fake_funasr = MagicMock()
        fake_funasr.AutoModel = fake_auto_model_cls
        monkeypatch.setitem(__import__("sys").modules, "funasr", fake_funasr)

        engine._get_or_load_model("cn_meeting")

        profile = get_profile_spec(JobProfile.CN_MEETING)
        assert profile.asr_model_id in captured_kwargs["model"] or captured_kwargs["model"] == profile.asr_model_id
        assert (
            profile.vad_model_id in captured_kwargs["vad_model"] or captured_kwargs["vad_model"] == profile.vad_model_id
        )
        assert captured_kwargs["device"] == "cpu"
        assert captured_kwargs["trust_remote_code"] is True

    def test_loader_raises_unavailable_without_funasr(self, inference_settings: Settings, monkeypatch) -> None:
        """funasr 未安装时应抛出 FunASRUnavailableError。"""
        pool: TTLModelPool[Any] = TTLModelPool(ttl_seconds=600)
        engine = FunASREngine(settings=inference_settings, model_pool=pool)

        monkeypatch.delitem(__import__("sys").modules, "funasr", raising=False)
        monkeypatch.setattr(
            "builtins.__import__",
            _make_import_blocker("funasr"),
        )

        with pytest.raises(FunASRUnavailableError, match="not installed"):
            engine._get_or_load_model("cn_meeting")


def _make_import_blocker(blocked_name: str):
    """创建一个 import 拦截器，阻止指定模块的导入。"""
    import builtins

    original_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == blocked_name:
            raise ImportError(f"No module named '{blocked_name}'")
        return original_import(name, *args, **kwargs)

    return _blocked_import
