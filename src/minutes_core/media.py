from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from minutes_core.constants import NORMALIZED_CHANNELS, NORMALIZED_SAMPLE_RATE

# 子进程超时时间（5 分钟）
_SUBPROCESS_TIMEOUT_SECONDS = 300


class MediaProcessingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaProbe:
    duration_ms: int
    format_name: str


def probe_media(input_path: Path) -> MediaProbe:
    """探测媒体文件信息（时长、格式）。"""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name",
        "-of",
        "json",
        str(input_path),
    ]
    logger.debug("Running ffprobe on {}", input_path)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out after {}s for {}", _SUBPROCESS_TIMEOUT_SECONDS, input_path)
        raise MediaProcessingError(f"ffprobe timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s") from None
    if result.returncode != 0:
        logger.warning("ffprobe failed for {}: {}", input_path, result.stderr.strip())
        raise MediaProcessingError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    duration = float(payload["format"]["duration"])
    format_name = str(payload["format"].get("format_name", "unknown"))
    logger.info("Probed {}: duration={}ms, format={}", input_path, int(duration * 1000), format_name)
    return MediaProbe(duration_ms=int(duration * 1000), format_name=format_name)


def transcode_to_wav(input_path: Path, output_path: Path) -> Path:
    """将音频转码为 16k 单声道 WAV 格式。"""
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(NORMALIZED_CHANNELS),
        "-ar",
        str(NORMALIZED_SAMPLE_RATE),
        str(output_path),
    ]
    logger.debug("Running ffmpeg: {} -> {}", input_path, output_path)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out after {}s for {}", _SUBPROCESS_TIMEOUT_SECONDS, input_path)
        raise MediaProcessingError(f"ffmpeg timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s") from None
    if result.returncode != 0:
        logger.warning("ffmpeg failed for {}: {}", input_path, result.stderr.strip())
        raise MediaProcessingError(result.stderr.strip() or "ffmpeg failed")
    logger.info("Transcoded {} -> {}", input_path, output_path)
    return output_path
