"""RemoteSTTEngine 分支覆盖补充测试 — hotwords 传递与 response.json() 解析失败回退。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minutes_core.profiles import JobProfile
from minutes_core.schemas import JobDetail
from minutes_inference.engines.remote_stt import RemoteSTTEngine, RemoteSTTError


def _make_job(
    tmp_path: Path, *, hotwords: list[str] | None = None, profile: JobProfile = JobProfile.CN_MEETING
) -> JobDetail:
    """构造带 hotwords 的 JobDetail。"""
    from datetime import datetime

    return JobDetail(
        id="job-hw-1",
        status="transcribing",
        profile=profile,
        source_filename="test.wav",
        source_path=str(tmp_path / "test.wav"),
        output_dir=str(tmp_path / "output"),
        normalized_path=str(tmp_path / "normalized.wav"),
        duration_ms=3000,
        progress=50,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        hotwords=hotwords or [],
    )


def _mock_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    resp.text = json.dumps(body or {})
    return resp


class TestHotwordsPassthrough:
    """测试 hotwords 在 supports_hotwords=True 的 profile 下被正确传递。"""

    def test_hotwords_included_for_cn_meeting_profile(self, tmp_path: Path) -> None:
        """验证 cn_meeting profile (supports_hotwords=True) 时，hotwords 被加入 multipart data。"""
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake-audio-data")
        job = _make_job(tmp_path, hotwords=["人工智能", "大模型"])

        verbose_response = {
            "text": "你好",
            "language": "zh",
            "duration": 1.0,
            "segments": [],
            "x_speakers": [],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200, verbose_response)

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            engine.transcribe(job, wav)

        call_kwargs = mock_client.post.call_args
        data = call_kwargs.kwargs["data"]
        assert "hotwords" in data
        assert data["hotwords"] == "人工智能,大模型"

    def test_hotwords_omitted_for_unsupported_profile(self, tmp_path: Path) -> None:
        """验证 multilingual_rich profile (supports_hotwords=False) 时，hotwords 不传递。"""
        wav = tmp_path / "normalized.wav"
        wav.write_bytes(b"fake-audio-data")
        job = _make_job(tmp_path, hotwords=["keyword"], profile=JobProfile.MULTILINGUAL_RICH)

        verbose_response = {
            "text": "hello",
            "language": "en",
            "duration": 1.0,
            "segments": [],
            "x_speakers": [],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200, verbose_response)

        engine = RemoteSTTEngine(base_url="http://stt:8000", api_key=None, timeout=600)

        with patch("minutes_inference.engines.remote_stt.httpx.Client", return_value=mock_client):
            engine.transcribe(job, wav)

        call_kwargs = mock_client.post.call_args
        data = call_kwargs.kwargs["data"]
        assert "hotwords" not in data


class TestCheckResponseJsonFallback:
    """测试 _check_response 中 response.json() 解析失败回退到 response.text 的分支。"""

    @pytest.mark.parametrize(
        "status_code,json_side_effect,text,expected_exc",
        [
            (400, ValueError("No JSON object could be decoded"), "Bad Request: unsupported format", RemoteSTTError),
            (502, Exception("parse error"), "Bad Gateway", RuntimeError),
            (401, ValueError("Not JSON"), "Unauthorized", RemoteSTTError),
        ],
        ids=["bad-request-non-json", "server-error-non-json", "auth-error-non-json"],
    )
    def test_non_json_error_falls_back_to_text(
        self,
        status_code: int,
        json_side_effect: Exception,
        text: str,
        expected_exc: type[Exception],
    ) -> None:
        """验证当 response.json() 抛异常时，使用 response.text 作为 detail。"""
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.side_effect = json_side_effect
        resp.text = text

        with pytest.raises(expected_exc, match=text):
            RemoteSTTEngine._check_response(resp)
