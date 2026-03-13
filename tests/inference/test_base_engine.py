"""InferenceEngine Protocol 定义测试。"""

from __future__ import annotations

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


def test_concrete_engines_have_matching_transcribe_signature() -> None:
    """验证 FakeInferenceEngine 和 RemoteSTTEngine 都实现了 transcribe 方法。"""
    from minutes_inference.engines.fake import FakeInferenceEngine
    from minutes_inference.engines.remote_stt import RemoteSTTEngine

    # 确保两个引擎都有 transcribe 方法
    assert callable(getattr(FakeInferenceEngine, "transcribe", None))
    assert callable(getattr(RemoteSTTEngine, "transcribe", None))

    # 确保方法签名中包含必要的参数
    for engine_cls in (FakeInferenceEngine, RemoteSTTEngine):
        ann = engine_cls.transcribe.__annotations__
        assert "job" in ann
        assert "normalized_path" in ann
        assert "return" in ann
