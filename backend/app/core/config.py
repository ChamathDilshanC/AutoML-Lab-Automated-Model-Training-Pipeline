from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AutoML Lab"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./automl.db"
    artifact_dir: str = "./artifacts"
    # Proposed default; the real limit is an open decision (docs/PRD.md, NFR-005).
    max_upload_bytes: int = 10 * 1024 * 1024
    # Worker settings. Both values are proposed defaults.
    worker_poll_seconds: float = 2.0
    job_timeout_seconds: int = 1800
    reaper_interval_seconds: float = 60.0
    # Model limits, also proposed defaults.
    max_prediction_batch: int = 100
    max_artifact_bytes: int = 200 * 1024 * 1024
    # Authentication and abuse limits (proposed defaults).
    secret_key: str | None = None
    access_token_minutes: int = 60
    predict_rate_limit_per_minute: int = 60
    login_rate_limit_per_minute: int = 10
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
