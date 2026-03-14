"""logging.py 的单元测试：InterceptHandler 和 bind_request_context。"""

from __future__ import annotations

import logging

from minutes_core.logging import (
    InterceptHandler,
    _record_patch,
    bind_request_context,
    clear_request_context,
    job_id_var,
    request_id_var,
)


def test_intercept_handler_valid_level() -> None:
    """InterceptHandler 对标准 level name 应正常路由到 loguru。"""
    handler = InterceptHandler()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="test warning",
        args=(),
        exc_info=None,
    )
    # 不应抛出异常
    handler.emit(record)


def test_intercept_handler_invalid_level_falls_back_to_levelno() -> None:
    """InterceptHandler 遇到无法识别的 level name 时，应回退使用 levelno。"""
    handler = InterceptHandler()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="test message",
        args=(),
        exc_info=None,
    )
    # 篡改 levelName 为一个 loguru 无法识别的值
    record.levelname = "NONEXISTENT_LEVEL"
    # 不应抛出 ValueError，应回退到 levelno
    handler.emit(record)


def test_bind_request_context_sets_request_id() -> None:
    """bind_request_context 应将 request_id 设置到 ContextVar 中。"""
    bind_request_context(request_id="req-abc")
    assert request_id_var.get() == "req-abc"


def test_bind_request_context_sets_job_id() -> None:
    """bind_request_context 应将 job_id 设置到 ContextVar 中。"""
    bind_request_context(job_id="job-xyz")
    assert job_id_var.get() == "job-xyz"


def test_bind_request_context_sets_both() -> None:
    """bind_request_context 同时设置 request_id 和 job_id。"""
    result = bind_request_context(request_id="req-123", job_id="job-456")
    assert request_id_var.get() == "req-123"
    assert job_id_var.get() == "job-456"
    # 返回值应该是 loguru 的 logger 实例（带 bind）
    assert result is not None


def test_bind_request_context_skips_none_values() -> None:
    """bind_request_context 不传参数时不应修改 ContextVar。"""
    # 先设置一个已知值
    request_id_var.set("existing-req")
    job_id_var.set("existing-job")
    bind_request_context()
    # 值应保持不变
    assert request_id_var.get() == "existing-req"
    assert job_id_var.get() == "existing-job"


def test_record_patch_injects_context_values() -> None:
    """_record_patch 应把 ContextVar 中的 request/job id 写入 extra。"""
    request_id_var.set("req-ctx")
    job_id_var.set("job-ctx")
    record = {"extra": {"service": "gateway"}}

    _record_patch(record)

    assert record["extra"]["service"] == "gateway"
    assert record["extra"]["request_id"] == "req-ctx"
    assert record["extra"]["job_id"] == "job-ctx"


def test_record_patch_sets_default_service_when_missing() -> None:
    """_record_patch 在无 service 时应补默认值，保证日志结构稳定。"""
    request_id_var.set(None)
    job_id_var.set(None)
    record = {}

    _record_patch(record)

    assert record["extra"]["service"] == "unknown"
    assert record["extra"]["request_id"] is None
    assert record["extra"]["job_id"] is None


def test_clear_request_context_resets_values() -> None:
    """clear_request_context 应清空上下文字段，避免跨请求污染。"""
    bind_request_context(request_id="req-clean", job_id="job-clean")

    clear_request_context()

    assert request_id_var.get() is None
    assert job_id_var.get() is None
