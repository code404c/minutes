"""config.py 的单元测试：关键稳定性配置校验。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from minutes_core.config import Settings


def test_settings_normalizes_log_level() -> None:
    """log_level 应进行标准化，避免大小写差异带来的行为不一致。"""
    settings = Settings(log_level=" warning ")
    assert settings.log_level == "WARNING"


def test_settings_rejects_invalid_log_level() -> None:
    """log_level 无效值应在启动阶段快速失败。"""
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_settings_rejects_invalid_port() -> None:
    """端口范围应被限制在合法 TCP 端口范围。"""
    with pytest.raises(ValidationError):
        Settings(port=0)


def test_settings_rejects_non_positive_timeout() -> None:
    """超时参数必须大于 0，避免运行时立即超时或无限等待。"""
    with pytest.raises(ValidationError):
        Settings(stt_timeout_seconds=0)


def test_settings_rejects_non_positive_sqlite_busy_timeout() -> None:
    """SQLite busy timeout 必须为正数。"""
    with pytest.raises(ValidationError):
        Settings(sqlite_busy_timeout_ms=0)


def test_settings_normalizes_log_level_aliases() -> None:
    """常见日志级别别名应被兼容，以降低迁移风险。"""
    assert Settings(log_level="warn").log_level == "WARNING"
    assert Settings(log_level="fatal").log_level == "CRITICAL"
