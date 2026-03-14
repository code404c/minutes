"""app.py 的 lifespan、main() 和 middleware 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestLifespanClosesEventBus:
    """lifespan 生命周期在关闭时应调用 event_bus.close()。"""

    def test_event_bus_close_called_on_shutdown(self, gateway_harness_factory) -> None:
        """验证应用关闭时，lifespan 的 finally 块调用了 event_bus.close()。"""
        with gateway_harness_factory() as harness:
            # 添加 close 方法到 event_bus，使其被 lifespan 识别
            harness.event_bus.close = MagicMock(name="event_bus_close")
            harness.app.state.event_bus = harness.event_bus

            # TestClient 的 __exit__ 会触发 lifespan 的 shutdown 阶段
            # 在 context manager 内部验证 close 尚未被调用
            harness.event_bus.close.assert_not_called()

        # context manager 退出后，lifespan 的 finally 块应已执行
        harness.event_bus.close.assert_called_once()

    def test_lifespan_works_without_close_method(self, gateway_harness_factory) -> None:
        """验证 event_bus 没有 close 方法时 lifespan 不会报错。"""
        with gateway_harness_factory() as harness:
            # FakeEventBus 默认没有 close 方法，确认不会抛异常
            assert not hasattr(harness.event_bus, "close") or not callable(getattr(harness.event_bus, "close", None))
            # 正常使用即可
            response = harness.client.get("/health")
            assert response.status_code == 200
        # 如果运行到这里没有抛异常就说明通过


class TestRequestContextCleanup:
    """middleware 应在请求结束后清理上下文。"""

    def test_request_context_is_cleared_after_request(self, gateway_harness_factory) -> None:
        """验证请求处理完成后 clear_request_context 被调用。"""
        with gateway_harness_factory() as harness:
            with patch("minutes_gateway.app.clear_request_context") as mock_clear:
                response = harness.client.get("/health")
                assert response.status_code == 200
                mock_clear.assert_called_once()


class TestMain:
    """main() 入口函数测试。"""

    def test_main_calls_uvicorn_run(self) -> None:
        """验证 main() 调用 uvicorn.run 并传入正确参数。"""
        mock_uvicorn = MagicMock()
        mock_settings = MagicMock()
        mock_settings.host = "127.0.0.1"
        mock_settings.port = 9999

        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch("minutes_gateway.app.get_settings", return_value=mock_settings),
        ):
            from minutes_gateway.app import main

            main()

        mock_uvicorn.run.assert_called_once_with(
            "minutes_gateway.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=9999,
            reload=False,
        )
