"""InferenceEngine Protocol 定义测试。"""

from __future__ import annotations

import pytest

from minutes_inference.engines.base import InferenceEngine


def test_inference_engine_protocol_defines_transcribe_method() -> None:
    """验证 InferenceEngine Protocol 声明了 transcribe 方法签名。"""
    assert hasattr(InferenceEngine, "transcribe")
    # Protocol 中 transcribe 接受 (self, job: JobDetail, normalized_path: Path) -> TranscriptDocument
    # 使用 __annotations__ (因为 from __future__ import annotations 使值为字符串)
    annotations = InferenceEngine.transcribe.__annotations__
    assert "job" in annotations
    assert "normalized_path" in annotations
    assert "return" in annotations


def test_inference_engine_is_protocol_class() -> None:
    """验证 InferenceEngine 是一个 Protocol 类。"""
    assert getattr(InferenceEngine, "_is_protocol", False) is True


@pytest.mark.parametrize(
    "engine_cls_path",
    [
        "minutes_inference.engines.fake.FakeInferenceEngine",
        "minutes_inference.engines.remote_stt.RemoteSTTEngine",
    ],
    ids=["fake-engine", "remote-stt-engine"],
)
def test_concrete_engine_has_matching_transcribe_signature(engine_cls_path: str) -> None:
    """验证具体引擎实现了 transcribe 方法且签名匹配。"""
    import importlib

    module_path, cls_name = engine_cls_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    engine_cls = getattr(module, cls_name)

    assert callable(getattr(engine_cls, "transcribe", None))

    ann = engine_cls.transcribe.__annotations__
    assert "job" in ann
    assert "normalized_path" in ann
    assert "return" in ann
