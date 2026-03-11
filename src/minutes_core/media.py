from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from minutes_core.constants import NORMALIZED_CHANNELS, NORMALIZED_SAMPLE_RATE


class MediaProcessingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaProbe:
    duration_ms: int
    format_name: str


def probe_media(input_path: Path) -> MediaProbe:
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
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaProcessingError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    duration = float(payload["format"]["duration"])
    format_name = str(payload["format"].get("format_name", "unknown"))
    return MediaProbe(duration_ms=int(duration * 1000), format_name=format_name)


def transcode_to_wav(input_path: Path, output_path: Path) -> Path:
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
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaProcessingError(result.stderr.strip() or "ffmpeg failed")
    return output_path

