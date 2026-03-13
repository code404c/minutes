"""queue.py 的单元测试：DramatiqQueueDispatcher 的三个 enqueue 方法。"""

from __future__ import annotations

from unittest.mock import MagicMock

from minutes_core.queue import DramatiqQueueDispatcher


def test_enqueue_prepare_job(monkeypatch) -> None:
    """enqueue_prepare_job 应惰性导入 prepare_job_actor 并调用 send()。"""
    fake_actor = MagicMock()
    fake_module = MagicMock()
    fake_module.prepare_job_actor = fake_actor

    monkeypatch.setattr(
        "minutes_core.queue.DramatiqQueueDispatcher.enqueue_prepare_job.__module__",
        "minutes_core.queue",
    )

    # 直接替换 import 的目标模块
    import sys

    monkeypatch.setitem(sys.modules, "minutes_orchestrator.actors", fake_module)

    dispatcher = DramatiqQueueDispatcher()
    dispatcher.enqueue_prepare_job("job-001")

    fake_actor.send.assert_called_once_with("job-001")


def test_enqueue_finalize_job(monkeypatch) -> None:
    """enqueue_finalize_job 应惰性导入 finalize_job_actor 并调用 send()。"""
    fake_actor = MagicMock()
    fake_module = MagicMock()
    fake_module.finalize_job_actor = fake_actor

    import sys

    monkeypatch.setitem(sys.modules, "minutes_orchestrator.actors", fake_module)

    dispatcher = DramatiqQueueDispatcher()
    dispatcher.enqueue_finalize_job("job-002")

    fake_actor.send.assert_called_once_with("job-002")


def test_enqueue_transcription_job(monkeypatch) -> None:
    """enqueue_transcription_job 应惰性导入 transcribe_job_actor 并调用 send()。"""
    fake_actor = MagicMock()
    fake_module = MagicMock()
    fake_module.transcribe_job_actor = fake_actor

    import sys

    monkeypatch.setitem(sys.modules, "minutes_inference.actors", fake_module)

    dispatcher = DramatiqQueueDispatcher()
    dispatcher.enqueue_transcription_job("job-003")

    fake_actor.send.assert_called_once_with("job-003")
