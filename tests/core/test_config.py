"""config.py 的单元测试：Field 约束和 log_level 标准化。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from minutes_core.config import Settings


class TestLogLevelNormalization:
    """log_level field_validator 标准化测试。"""

    def test_warn_normalized_to_warning(self) -> None:
        """WARN 应被标准化为 WARNING。"""
        s = Settings(log_level="WARN")
        assert s.log_level == "WARNING"

    def test_fatal_normalized_to_critical(self) -> None:
        """FATAL 应被标准化为 CRITICAL。"""
        s = Settings(log_level="FATAL")
        assert s.log_level == "CRITICAL"

    def test_lowercase_normalized_to_uppercase(self) -> None:
        """小写 debug 应被标准化为 DEBUG。"""
        s = Settings(log_level="debug")
        assert s.log_level == "DEBUG"

    def test_standard_level_unchanged(self) -> None:
        """标准级别 INFO 保持不变。"""
        s = Settings(log_level="INFO")
        assert s.log_level == "INFO"


class TestFieldConstraints:
    """Field 约束验证测试。"""

    def test_invalid_port_rejected(self) -> None:
        """port 超出范围应被拒绝。"""
        with pytest.raises(ValidationError):
            Settings(port=0)
        with pytest.raises(ValidationError):
            Settings(port=70000)

    def test_timeout_zero_rejected(self) -> None:
        """sync_wait_timeout_s <= 0 应被拒绝。"""
        with pytest.raises(ValidationError):
            Settings(sync_wait_timeout_s=0)

    def test_sqlite_busy_zero_rejected(self) -> None:
        """sqlite_busy_timeout_ms <= 0 应被拒绝。"""
        with pytest.raises(ValidationError):
            Settings(sqlite_busy_timeout_ms=0)

    def test_stt_timeout_zero_rejected(self) -> None:
        """stt_timeout_seconds <= 0 应被拒绝。"""
        with pytest.raises(ValidationError):
            Settings(stt_timeout_seconds=0)

    def test_alias_compatibility(self) -> None:
        """通过环境变量前缀兼容性测试：默认值应正常加载。"""
        s = Settings()
        assert s.port == 8000
        assert s.sync_wait_timeout_s > 0
        assert s.sqlite_busy_timeout_ms == 5000
        assert s.stt_timeout_seconds == 600
