from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from minutes_core.constants import DEFAULT_SYNC_WAIT_TIMEOUT_S
from minutes_core.profiles import JobProfile


class Settings(BaseSettings):
    """
    应用程序配置类。
    支持从环境变量（前缀为 MINUTES_）或 .env 文件中读取。
    """

    model_config = SettingsConfigDict(env_prefix="MINUTES_", env_file=".env", extra="ignore")

    # 服务基本信息
    service_name: str = "minutes"
    log_level: str = "INFO"
    log_json: bool = True

    # 网络配置
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # 外部依赖连接
    database_url: str = "sqlite:///data/app/app.db"
    redis_url: str = "redis://redis:6379/0"

    # 存储路径
    storage_root: Path = Path("data/app")

    # 安全配置
    api_key: SecretStr | None = None  # API 访问密钥

    # 业务逻辑默认配置
    default_profile: JobProfile = JobProfile.CN_MEETING  # 默认转写任务配置方案
    sync_wait_timeout_s: int = Field(default=DEFAULT_SYNC_WAIT_TIMEOUT_S, ge=1)  # 同步模式等待超时时间（秒）
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1)  # SQLite 忙等待超时（毫秒）

    # STT 远程推理配置
    stt_base_url: str = "http://localhost:8101"  # STT 服务地址
    stt_api_key: SecretStr | None = None  # STT 服务 API key
    stt_timeout_seconds: int = Field(default=600, ge=1)  # 单次转写超时（秒）
    gateway_public_base_url: str = "http://localhost:8000"  # 网关服务的公共访问 URL
    fake_inference: bool = False  # 是否使用模拟推理（测试用）

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """标准化日志级别：WARN→WARNING, FATAL→CRITICAL。"""
        mapping = {"WARN": "WARNING", "FATAL": "CRITICAL"}
        return mapping.get(v.upper(), v.upper())

    @property
    def uploads_dir(self) -> Path:
        """上传文件存储目录"""
        return self.storage_root / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        """任务生成的中间文件/最终结果存储目录"""
        return self.storage_root / "artifacts"


@lru_cache
def get_settings() -> Settings:
    """
    以单例模式获取全局配置设置。
    """
    return Settings()
