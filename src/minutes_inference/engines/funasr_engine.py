from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from minutes_core.config import Settings
from minutes_core.profiles import get_profile_spec
from minutes_core.schemas import JobDetail, Segment, Speaker, TranscriptDocument
from minutes_inference.model_pool import TTLModelPool


class FunASRUnavailableError(RuntimeError):
    """当未安装 FunASR 库时抛出的异常。"""

    pass


class FunASREngine:
    """
    FunASR 推理引擎实现。

    该类实现了 InferenceEngine 协议，使用 FunASR 库进行音频转录。
    它支持 VAD（语音活动检测）、标点恢复和说话人识别（如果模型支持）。
    """

    def __init__(self, *, settings: Settings, model_pool: TTLModelPool[Any]) -> None:
        """
        初始化 FunASR 引擎。

        Args:
            settings: 全局配置对象。
            model_pool: 用于管理和缓存模型的 TTLModelPool 实例。
        """
        self.settings = settings
        self.model_pool = model_pool

    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument:
        """
        执行音频转录。

        该方法获取对应配置的模型，设置生成参数，并调用 FunASR 进行推理。

        Args:
            job: 任务详情。
            normalized_path: 待转录的标准化音频文件路径。

        Returns:
            TranscriptDocument: 转录结果文档。
        """
        # 获取任务对应的配置规格（Profile）
        profile = get_profile_spec(job.profile)
        # 从模型池中获取或加载模型
        model = self._get_or_load_model(profile.name.value)

        # 准备推理参数
        generate_kwargs: dict[str, Any] = {
            "input": str(normalized_path),
            "cache": {},
            "language": job.language or profile.default_language,
            "use_itn": True,  # 使用逆文本标准化
            "batch_size_s": 60,
            "merge_vad": True,
            "merge_length_s": 15,
        }
        # 如果任务提供了热词且配置支持热词，则加入推理参数
        if job.hotwords and profile.supports_hotwords:
            generate_kwargs["hotword"] = " ".join(job.hotwords)

        # 调用模型生成转录结果
        results = model.generate(**generate_kwargs)
        if not results:
            raise RuntimeError("FunASR returned no transcription results.")

        # 解析 FunASR 的返回结果
        item = results[0]
        full_text = str(item.get("text", "")).strip()
        sentence_info = item.get("sentence_info") or []

        # 构建转录分段（Segments）和说话人信息（Speakers）
        segments = self._build_segments(sentence_info, full_text, job.duration_ms or 0)
        speakers = self._build_speakers(segments)

        return TranscriptDocument(
            job_id=job.id,
            language=job.language or profile.default_language,
            full_text=full_text,
            segments=segments,
            paragraphs=[full_text] if full_text else [],
            speakers=speakers,
            model_profile=job.profile,
        )

    def _get_or_load_model(self, cache_key: str):
        """
        内部方法：从模型池获取或通过加载器创建模型。
        """

        def _loader():
            """FunASR 模型加载逻辑。"""
            try:
                from funasr import AutoModel
            except ImportError as exc:  # pragma: no cover - depends on optional package
                raise FunASRUnavailableError(
                    "FunASR is not installed. "
                    "Install the project with the `inference` extra to enable real transcription."
                ) from exc

            profile = get_profile_spec(cache_key)
            # 配置模型、VAD 模型、设备等
            model_kwargs: dict[str, Any] = {
                "model": self._resolve_model_path(profile.asr_model_id),
                "vad_model": self._resolve_model_path(profile.vad_model_id),
                "device": self.settings.inference_device,
                "trust_remote_code": True,
            }
            # 如果配置中有标点模型或说话人模型，则加入加载参数
            if profile.punc_model_id:
                model_kwargs["punc_model"] = self._resolve_model_path(profile.punc_model_id)
            if profile.speaker_model_id:
                model_kwargs["spk_model"] = self._resolve_model_path(profile.speaker_model_id)
            return AutoModel(**model_kwargs)

        return self.model_pool.get_or_create(cache_key, _loader)

    def _resolve_model_path(self, model_id: str) -> str:
        """解析模型路径。

        如果 model_cache_dir 下存在对应目录，返回本地路径；否则返回原始 model ID 走 ModelScope 下载。
        按优先级搜索：直接路径、ModelScope 新版 (models/) 和旧版 (hub/) 缓存布局。
        """
        cache = self.settings.model_cache_dir.expanduser()
        for prefix in ("", "models/", "hub/"):
            candidate = cache / prefix / model_id
            if candidate.is_dir():
                return str(candidate)
        return model_id

    @staticmethod
    def _build_segments(
        sentence_info: list[dict[str, Any]], fallback_text: str, fallback_duration_ms: int
    ) -> list[Segment]:
        """
        将 FunASR 的 sentence_info 转换为标准的 Segment 列表。
        """
        if not sentence_info:
            # 如果没有句子信息，返回一个包含全部文本的单一分段
            return [
                Segment(
                    start_ms=0,
                    end_ms=max(fallback_duration_ms, 1_000),
                    speaker_id="speaker_1",
                    text=fallback_text,
                    confidence=None,
                )
            ]

        segments: list[Segment] = []
        for index, item in enumerate(sentence_info, start=1):
            # 提取说话人 ID，默认为递增的 ID
            speaker_id = item.get("spk") or item.get("speaker") or f"speaker_{index}"
            start_ms = int(item.get("start", 0))
            end_ms = int(item.get("end", start_ms + 1000))
            segments.append(
                Segment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    speaker_id=str(speaker_id),
                    text=str(item.get("text", "")).strip(),
                    confidence=item.get("confidence"),
                )
            )
        return segments

    @staticmethod
    def _build_speakers(segments: list[Segment]) -> list[Speaker]:
        """
        根据分段信息汇总说话人统计数据。
        """
        totals: Counter[str] = Counter()
        counts: Counter[str] = Counter()
        for segment in segments:
            if segment.speaker_id is None:
                continue
            totals[segment.speaker_id] += segment.end_ms - segment.start_ms
            counts[segment.speaker_id] += 1
        return [
            Speaker(
                speaker_id=speaker_id,
                display_name=speaker_id.replace("_", " ").title(),
                segment_count=counts[speaker_id],
                total_ms=totals[speaker_id],
            )
            for speaker_id in sorted(counts)
        ]
