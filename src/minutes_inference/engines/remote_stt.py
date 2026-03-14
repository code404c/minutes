"""通过 HTTP 调用任意 OpenAI-compatible STT 服务。"""

from __future__ import annotations

from pathlib import Path

import httpx
from loguru import logger

from minutes_core.profiles import get_profile_spec
from minutes_core.schemas import JobDetail, TranscriptDocument
from minutes_inference.engines.adapter import verbose_json_to_transcript


class RemoteSTTError(RuntimeError):
    """STT 服务返回了不可重试的错误。"""

    def __init__(self, message: str, *, status_code: int, error_code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RemoteSTTEngine:
    """通过 HTTP 调用任意 OpenAI-compatible STT 服务。"""

    def __init__(self, *, base_url: str, api_key: str | None, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=timeout, write=60.0, pool=30.0),
        )

    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument:
        profile = get_profile_spec(job.profile)

        # 构建 multipart 请求
        files = {"file": (normalized_path.name, normalized_path.read_bytes(), "audio/wav")}
        data: dict[str, str] = {
            "model": job.profile,
            "response_format": "verbose_json",
        }
        language = job.language or profile.default_language
        if language:
            data["language"] = language
        if job.hotwords and profile.supports_hotwords:
            data["hotwords"] = ",".join(job.hotwords)

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/v1/audio/transcriptions"
        logger.info("Calling STT service: url={} model={} language={}", url, job.profile, language)

        try:
            response = self._client.post(url, files=files, data=data, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("STT service timed out after {}s: url={}", self.timeout, url)
            raise RuntimeError(f"STT service timed out after {self.timeout}s") from exc
        except httpx.ConnectError as exc:
            logger.warning("Cannot connect to STT service at {}", self.base_url)
            raise RuntimeError(f"Cannot connect to STT service at {self.base_url}") from exc

        logger.debug("STT service responded with status {}: url={}", response.status_code, url)
        self._check_response(response)
        body = response.json()

        return verbose_json_to_transcript(body, job_id=job.id, profile=job.profile)

    def close(self) -> None:
        """关闭底层 HTTP 连接池。"""
        self._client.close()

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        """将 HTTP 错误映射为适当的异常类型。"""
        if response.status_code == 200:
            return

        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text

        status = response.status_code

        # 不可重试的客户端错误
        if status in (400, 422):
            raise RemoteSTTError(
                f"STT bad request: {detail}",
                status_code=status,
                error_code="INFERENCE_BAD_REQUEST",
            )
        if status in (401, 403):
            raise RemoteSTTError(
                f"STT authentication failed: {detail}",
                status_code=status,
                error_code="INFERENCE_AUTH_FAILED",
            )

        # 可重试的服务端错误 — 抛 RuntimeError 让 Dramatiq 重试
        raise RuntimeError(f"STT service error (HTTP {status}): {detail}")
