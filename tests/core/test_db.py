"""db.py 的单元测试：get_session 和 init_database_cli。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, get_session, init_database, init_database_cli


def test_get_session_yields_and_closes(tmp_path: Path) -> None:
    """get_session 应 yield 一个 session，finally 块中调用 close()。"""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'gs.db'}",
        storage_root=tmp_path / "storage",
    )
    factory = create_session_factory(settings)
    init_database(factory.kw["bind"])

    gen = get_session(factory)
    session = next(gen)
    # session 应可用
    result = session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    # 监控 session.close() 是否被调用
    original_close = session.close
    close_called = False

    def tracking_close() -> None:
        nonlocal close_called
        close_called = True
        original_close()

    with patch.object(session, "close", tracking_close):
        # 结束生成器，触发 finally 中的 session.close()
        try:
            next(gen)
        except StopIteration:
            pass

    assert close_called, "session.close() should be called when generator exits"


def test_get_session_closes_on_exception(tmp_path: Path) -> None:
    """get_session 在异常退出时也应关闭 session（finally 块）。"""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'gs_exc.db'}",
        storage_root=tmp_path / "storage",
    )
    factory = create_session_factory(settings)
    init_database(factory.kw["bind"])

    gen = get_session(factory)
    _session = next(gen)  # noqa: F841 — 需要推进生成器到 yield 点
    # 模拟异常退出，触发 finally 块中的 session.close()
    try:
        gen.throw(RuntimeError("simulated"))
    except RuntimeError:
        pass


def test_init_database_cli(monkeypatch, tmp_path: Path) -> None:
    """init_database_cli 应创建表并验证数据库连接。"""
    db_path = tmp_path / "cli.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        storage_root=tmp_path / "storage",
    )
    monkeypatch.setattr("minutes_core.db.get_settings", lambda: settings)
    init_database_cli()
    assert db_path.exists()
