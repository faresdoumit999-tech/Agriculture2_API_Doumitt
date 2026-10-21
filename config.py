"""Application configuration loaded strictly from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for DOUMITT Agricultural ERP.

    Values are read from environment variables and/or a local ``.env`` file.
    Secrets are never hardcoded; ``SECRET_KEY`` is mandatory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "DOUMITT Agricultural ERP"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False

    # Security
    secret_key: str = Field(min_length=16)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Infrastructure
    database_url: str = "postgresql+asyncpg://doumitt:doumitt@db:5432/doumitt"
    redis_url: str = "redis://redis:6379/0"

    # Caching
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_storage_uri: str = "memory://"
    login_rate_limit: str = "5/minute"
    report_rate_limit: str = "20/minute"

    # Observability
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0

    @property
    def cors_origins(self) -> list[str]:
        """Parse the comma separated ``ALLOWED_ORIGINS`` variable."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
