from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "kb-platform"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://kb_platform:kb_platform@localhost:5432/kb_platform"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: AnyUrl = AnyUrl("http://localhost:6333")

    minio_endpoint_url: AnyUrl = AnyUrl("http://localhost:9000")
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "kb-platform"
    embedding_endpoint_url: AnyUrl = AnyUrl("http://localhost:7997")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    prometheus_metrics_enabled: bool = True
    dependency_health_checks_enabled: bool = True
    dependency_health_timeout_seconds: float = 2.0
    database_pool_size: int = 5
    database_max_overflow: int = 10

    jwt_secret_key: SecretStr = SecretStr("change-me-in-production-with-at-least-32-bytes")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    default_api_key_rate_limit: int = 100


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings."""

    return Settings()
