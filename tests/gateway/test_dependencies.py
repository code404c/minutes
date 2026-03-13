"""dependencies.py 的依赖注入函数单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from minutes_gateway.dependencies import (
    get_db_session,
    get_event_bus,
    get_queue_dispatcher,
    get_session_factory,
    get_settings,
    get_storage_manager,
)


def _make_request(**state_attrs: object) -> MagicMock:
    """构建一个带有 app.state 属性的 mock Request 对象。"""
    request = MagicMock()
    for attr, value in state_attrs.items():
        setattr(request.app.state, attr, value)
    return request


class TestGetSettings:
    """get_settings 依赖函数测试。"""

    def test_returns_settings_from_app_state(self) -> None:
        sentinel = MagicMock(name="settings")
        request = _make_request(settings=sentinel)

        result = get_settings(request)

        assert result is sentinel


class TestGetSessionFactory:
    """get_session_factory 依赖函数测试。"""

    def test_returns_session_factory_from_app_state(self) -> None:
        sentinel = MagicMock(name="session_factory")
        request = _make_request(session_factory=sentinel)

        result = get_session_factory(request)

        assert result is sentinel


class TestGetDbSession:
    """get_db_session 依赖函数测试。"""

    def test_yields_session_and_closes_on_normal_exit(self) -> None:
        mock_session = MagicMock(name="session")
        mock_factory = MagicMock(return_value=mock_session)
        request = _make_request(session_factory=mock_factory)

        gen = get_db_session(request)
        session = next(gen)

        assert session is mock_session
        mock_session.close.assert_not_called()

        # 正常退出生成器
        with pytest.raises(StopIteration):
            next(gen)

        mock_session.close.assert_called_once()

    def test_closes_session_even_on_exception(self) -> None:
        mock_session = MagicMock(name="session")
        mock_factory = MagicMock(return_value=mock_session)
        request = _make_request(session_factory=mock_factory)

        gen = get_db_session(request)
        next(gen)

        # 模拟异常场景：向生成器注入异常
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("simulated error"))

        mock_session.close.assert_called_once()


class TestGetStorageManager:
    """get_storage_manager 依赖函数测试。"""

    def test_returns_storage_manager_from_app_state(self) -> None:
        sentinel = MagicMock(name="storage_manager")
        request = _make_request(storage_manager=sentinel)

        result = get_storage_manager(request)

        assert result is sentinel


class TestGetQueueDispatcher:
    """get_queue_dispatcher 依赖函数测试。"""

    def test_returns_queue_dispatcher_from_app_state(self) -> None:
        sentinel = MagicMock(name="queue_dispatcher")
        request = _make_request(queue_dispatcher=sentinel)

        result = get_queue_dispatcher(request)

        assert result is sentinel


class TestGetEventBus:
    """get_event_bus 依赖函数测试。"""

    def test_returns_event_bus_from_app_state(self) -> None:
        sentinel = MagicMock(name="event_bus")
        request = _make_request(event_bus=sentinel)

        result = get_event_bus(request)

        assert result is sentinel
