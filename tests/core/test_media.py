"""media.py 的单元测试：probe_media 和 transcode_to_wav。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from minutes_core.media import MediaProbe, MediaProcessingError, probe_media, transcode_to_wav

# ---------------------------------------------------------------------------
# probe_media
# ---------------------------------------------------------------------------


def _make_completed_process(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


FFPROBE_SUCCESS_PAYLOAD = json.dumps({"format": {"duration": "12.345", "format_name": "wav"}})


def test_probe_media_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ffprobe 成功返回 JSON 时，应解析出 MediaProbe 对象。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(stdout=FFPROBE_SUCCESS_PAYLOAD),
    )
    result = probe_media(tmp_path / "test.wav")
    assert isinstance(result, MediaProbe)
    assert result.duration_ms == 12345
    assert result.format_name == "wav"


def test_probe_media_success_missing_format_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """format_name 缺失时，应回退为 'unknown'。"""
    payload = json.dumps({"format": {"duration": "1.0"}})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(stdout=payload),
    )
    result = probe_media(tmp_path / "test.wav")
    assert result.format_name == "unknown"


def test_probe_media_nonzero_returncode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """returncode != 0 时，应抛出 MediaProcessingError 并包含 stderr 信息。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(returncode=1, stderr="  probe error  "),
    )
    with pytest.raises(MediaProcessingError, match="probe error"):
        probe_media(tmp_path / "bad.mp4")


def test_probe_media_ffprobe_failure_empty_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """returncode != 0 且 stderr 为空时，应使用回退消息 'ffprobe failed'。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(returncode=1, stderr=""),
    )
    with pytest.raises(MediaProcessingError, match="ffprobe failed"):
        probe_media(tmp_path / "bad.mp4")


def test_probe_media_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """subprocess.TimeoutExpired 应被转化为 MediaProcessingError。"""

    def _raise_timeout(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    with pytest.raises(MediaProcessingError, match="ffprobe timed out"):
        probe_media(tmp_path / "test.wav")


# ---------------------------------------------------------------------------
# transcode_to_wav
# ---------------------------------------------------------------------------


def test_transcode_to_wav_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ffmpeg 成功执行时，应返回 output_path。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(),
    )
    inp = tmp_path / "input.mp3"
    out = tmp_path / "output.wav"
    result = transcode_to_wav(inp, out)
    assert result == out


def test_transcode_to_wav_nonzero_returncode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ffmpeg returncode != 0 时，应抛出 MediaProcessingError。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(returncode=1, stderr="conversion error"),
    )
    with pytest.raises(MediaProcessingError, match="conversion error"):
        transcode_to_wav(tmp_path / "input.mp3", tmp_path / "output.wav")


def test_transcode_to_wav_nonzero_returncode_empty_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ffmpeg returncode != 0 且 stderr 为空时，应使用回退消息 'ffmpeg failed'。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_completed_process(returncode=1, stderr=""),
    )
    with pytest.raises(MediaProcessingError, match="ffmpeg failed"):
        transcode_to_wav(tmp_path / "input.mp3", tmp_path / "output.wav")


def test_transcode_to_wav_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """subprocess.TimeoutExpired 应被转化为 MediaProcessingError。"""

    def _raise_timeout(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=600)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    with pytest.raises(MediaProcessingError, match="ffmpeg timed out"):
        transcode_to_wav(tmp_path / "input.mp3", tmp_path / "output.wav")
