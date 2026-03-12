from __future__ import annotations

from pathlib import Path
from typing import Protocol

from minutes_core.schemas import JobDetail, TranscriptDocument


class InferenceEngine(Protocol):
    """
    推理引擎协议。

    该类定义了所有音频转录推理引擎必须实现的接口。通过使用 Protocol，
    我们可以实现结构化的子类型（鸭子类型），而无需显式继承。
    """

    def transcribe(self, job: JobDetail, normalized_path: Path) -> TranscriptDocument:
        """
        对给定的音频文件执行转录。

        Args:
            job: 包含任务元数据的 JobDetail 对象。
            normalized_path: 已经过预处理和标准化的音频文件路径。

        Returns:
            TranscriptDocument: 包含转录文本和相关元数据的文档对象。
        """
        ...
