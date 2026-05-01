from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "byob"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = Field(
        default="postgresql+asyncpg://byob:byob@localhost:5432/byob"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: AnyUrl = AnyUrl("http://localhost:6333")

    minio_endpoint_url: AnyUrl = AnyUrl("http://localhost:9000")
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "byob"
    embedding_endpoint_url: AnyUrl = AnyUrl("http://localhost:7997")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    pdf_parser: Literal["mineru", "pypdf"] = "mineru"
    mineru_command: str = "mineru"
    mineru_backend: str = "pipeline"
    mineru_parse_method: Literal["auto", "txt", "ocr"] = "auto"
    mineru_lang: str = "ch"
    mineru_timeout_seconds: int = 900
    mineru_api_url: str | None = None
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_fallback_to_pypdf: bool = True
    rerank_endpoint_url: AnyUrl = AnyUrl("http://localhost:7998")
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_enabled: bool = True
    retrieval_cache_ttl_seconds: int = 300
    mcp_server_url: AnyUrl = AnyUrl("http://127.0.0.1:8010/mcp")
    mcp_client_timeout_seconds: float = 60.0
    agent_llm_endpoint_url: AnyUrl | None = None
    agent_llm_api_key: SecretStr | None = None
    agent_llm_model: str = "qwen2.5:7b-instruct"
    agent_llm_timeout_seconds: float = 60.0
    agent_max_context_chars: int = 12000
    agent_max_image_assets: int = 3
    agent_max_image_bytes: int = 2_000_000
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

    @property
    def cors_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""

        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings."""

    return Settings()
