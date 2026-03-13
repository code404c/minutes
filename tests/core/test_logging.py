"""logging.py 的单元测试：InterceptHandler 和 bind_request_context。"""

from __future__ import annotations

import logging

from minutes_core.logging import InterceptHandler, bind_request_context, job_id_var, request_id_var


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
