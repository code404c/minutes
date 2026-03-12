from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from minutes_core.config import Settings
from minutes_core.profiles import get_profile_spec
from minutes_core.schemas import JobDetail, Segment, Speaker, TranscriptDocument
from minutes_inference.model_pool import TTLModelPool


class FunASRUnavailableError(RuntimeError):
    pass


class FunASREngine:
    def __init__(self, *, settings: Settings, model_pool: TTLModelPool[Any]) -> None:
        self.settings = settings
        self.model_pool = model_pool

    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument:
        profile = get_profile_spec(job.profile)
        model = self._get_or_load_model(profile.name.value)
        generate_kwargs: dict[str, Any] = {
            "input": str(normalized_path),
            "cache": {},
            "language": job.language or profile.default_language,
            "use_itn": True,
            "batch_size_s": 60,
            "merge_vad": True,
            "merge_length_s": 15,
        }
        if job.hotwords and profile.supports_hotwords:
            generate_kwargs["hotword"] = " ".join(job.hotwords)

        results = model.generate(**generate_kwargs)
        if not results:
            raise RuntimeError("FunASR returned no transcription results.")

        item = results[0]
        full_text = str(item.get("text", "")).strip()
        sentence_info = item.get("sentence_info") or []
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
        def _loader():
            try:
                from funasr import AutoModel
            except ImportError as exc:  # pragma: no cover - depends on optional package
                raise FunASRUnavailableError(
                    "FunASR is not installed. "
                    "Install the project with the `inference` extra to enable real transcription."
                ) from exc

            profile = get_profile_spec(cache_key)
            model_kwargs: dict[str, Any] = {
                "model": self._resolve_model_path(profile.asr_model_id),
                "vad_model": self._resolve_model_path(profile.vad_model_id),
                "device": self.settings.inference_device,
                "trust_remote_code": True,
            }
            if profile.punc_model_id:
                model_kwargs["punc_model"] = self._resolve_model_path(profile.punc_model_id)
            if profile.speaker_model_id:
                model_kwargs["spk_model"] = self._resolve_model_path(profile.speaker_model_id)
            return AutoModel(**model_kwargs)

        return self.model_pool.get_or_create(cache_key, _loader)

    def _resolve_model_path(self, model_id: str) -> str:
        """如果 model_cache_dir 下存在对应目录，返回本地路径；否则返回原始 model ID 走 ModelScope 下载。"""
        local = self.settings.model_cache_dir / model_id
        if local.is_dir():
            return str(local)
        return model_id

    @staticmethod
    def _build_segments(
        sentence_info: list[dict[str, Any]], fallback_text: str, fallback_duration_ms: int
    ) -> list[Segment]:
        if not sentence_info:
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
