"""Application settings, loaded once from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "supplier-service"
    environment: str = "local"

    # Persistence. Async driver is required: asyncpg in production, aiosqlite in tests.
    database_url: str = "postgresql+asyncpg://supplier:supplier@localhost:5432/supplier"
    database_echo: bool = False
    # Convenience for local runs and tests. A real deployment would apply
    # migrations (Alembic) as a deploy step and leave this off.
    create_schema_on_startup: bool = True

    # The upstream supplier directory this service ingests from.
    supplier_api_base_url: str = "https://directory.example.com"
    supplier_api_key: str | None = None
    supplier_api_timeout_seconds: float = 10.0
    supplier_api_max_attempts: int = 3

    # Enrichment. Without a key the service still runs; enrichment is marked skipped.
    anthropic_api_key: str | None = None
    enrichment_model: str = "claude-opus-5"

    # Background worker.
    worker_poll_interval_seconds: float = 2.0
    worker_batch_size: int = 5
    worker_max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
