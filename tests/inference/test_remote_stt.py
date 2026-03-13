"""RemoteSTTEngine 测试 — mock httpx。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from minutes_core.profiles import JobProfile
from minutes_core.schemas import JobDetail
from minutes_inference.engines.remote_stt import RemoteSTTEngine, RemoteSTTError


def _make_job(tmp_path: Path) -> JobDetail:
    """构造一个最小 JobDetail 用于测试。"""
    from datetime import datetime

    return JobDetail(
        id="job-test-1",
        status="transcribing",
        profile=JobProfile.CN_MEETING,
        source_filename="test.wav",
        source_path=str(tmp_path / "test.wav"),
        output_dir=str(tmp_path / "output"),
        normalized_path=str(tmp_path / "normalized.wav"),
        duration_ms=3000,
        progress=50,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _mock_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    resp.text = json.dumps(body or {})
    return resp


class TestRemoteSTTEngine:
    def test_transcribe_sends_correct_multipart(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake-audio-data")
        job = _make_job(tmp_path)

        verbose_response = {
            "text": "你好世界",
            "language": "zh",
            "duration": 3.0,
            "segments": [
                {"id": 0, "start": 0.0, "end": 1.5, "text": "你好", "x_speaker_id": "speaker_1"},
                {"id": 1, "start": 1.5, "end": 3.0, "text": "世界", "x_speaker_id": "speaker_2"},
            ],
            "x_speakers": [],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200, verbose_response)

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            doc = engine.transcribe(job, wav)

        assert doc.job_id == "job-test-1"
        assert doc.full_text == "你好世界"
        assert len(doc.segments) == 2
        assert doc.segments[0].start_ms == 0
        assert doc.segments[0].end_ms == 1500

        # 验证 POST 调用参数
        call_kwargs = mock_client.post.call_args
        assert "/v1/audio/transcriptions" in call_kwargs.args[0]
        assert call_kwargs.kwargs["data"]["model"] == "cn_meeting"
        assert call_kwargs.kwargs["data"]["response_format"] == "verbose_json"

    def test_transcribe_sends_auth_header(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake-audio-data")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200, {"text": "hi", "language": "en", "duration": 1.0})

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key="secret-key", timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            engine.transcribe(job, wav)

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer secret-key"

    def test_bad_request_raises_non_retryable(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(400, {"detail": "bad model"})

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            with pytest.raises(RemoteSTTError) as exc_info:
                engine.transcribe(job, wav)

        assert exc_info.value.error_code == "INFERENCE_BAD_REQUEST"

    def test_auth_error_raises_non_retryable(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(401, {"detail": "invalid key"})

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key="wrong", timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            with pytest.raises(RemoteSTTError) as exc_info:
                engine.transcribe(job, wav)

        assert exc_info.value.error_code == "INFERENCE_AUTH_FAILED"

    def test_server_error_raises_retryable(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(500, {"detail": "internal error"})

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="STT service error"):
                engine.transcribe(job, wav)

    def test_timeout_raises_retryable(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.TimeoutException("read timed out")

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=10)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="timed out"):
                engine.transcribe(job, wav)

    def test_connect_error_raises_retryable(self, tmp_path: Path) -> None:
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake")
        job = _make_job(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=10)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Cannot connect"):
                engine.transcribe(job, wav)
