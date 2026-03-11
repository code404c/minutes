from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from minutes_core.constants import DEFAULT_SYNC_WAIT_TIMEOUT_S
from minutes_core.profiles import JobProfile


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINUTES_", env_file=".env", extra="ignore")

    service_name: str = "minutes"
    log_level: str = "INFO"
    log_json: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "sqlite:///data/app/app.db"
    redis_url: str = "redis://redis:6379/0"
    storage_root: Path = Path("data/app")
    api_key: SecretStr | None = None
    default_profile: JobProfile = JobProfile.CN_MEETING
    sync_wait_timeout_s: int = DEFAULT_SYNC_WAIT_TIMEOUT_S
    sqlite_busy_timeout_ms: int = 5000
    model_cache_dir: Path = Path("/modelscope-cache")
    model_ttl_seconds: int = 900
    inference_device: str = "cuda:0"
    gateway_public_base_url: str = "http://localhost:8000"
    fake_inference: bool = False

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        return self.storage_root / "artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
