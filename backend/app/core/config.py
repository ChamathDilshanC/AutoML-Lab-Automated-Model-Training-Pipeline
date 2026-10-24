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
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
