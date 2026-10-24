from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

SQLITE_PREFIX = "sqlite"


def normalize_database_url(url: str) -> str:
    """Make `postgres://` and `postgresql://` use the psycopg 3 driver this project installs."""
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old) :]
    return url


class Settings(BaseSettings):
    """Application settings, read from environment variables and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AutoML Lab"
    environment: str = "local"
    log_level: str = "INFO"
    # Where metadata lives. SQLite is for ENVIRONMENT=local only; anywhere else a PostgreSQL
    # database is required, given either as one URL or as parts (so a password can come from a
    # secret store instead of being written into a URL).
    database_url: str = "sqlite:///./automl.db"
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "automl"
    db_user: str = "automl"
    db_password: SecretStr | None = None
    db_sslmode: str = "require"
    migration_wait_seconds: float = 300.0  # how long the worker waits for the API's migrations
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
    # How many reverse proxies sit in front of the API (App Runner adds one). 0 means none: the
    # X-Forwarded-For header is then ignored, so a client cannot spoof its address.
    trusted_proxy_hops: int = 0
    # Where files live and how jobs reach the worker. The defaults need no AWS account
    # (docs/ADR/0001, docs/ADR/0005).
    storage_mode: Literal["local", "s3"] = "local"
    job_mode: Literal["db", "sqs"] = "db"
    aws_region: str = "eu-west-1"
    s3_bucket: str | None = None
    s3_presign_expires_seconds: int = 300
    # "virtual" (bucket.s3.<region>.amazonaws.com) is right for AWS. S3-compatible emulators such
    # as LocalStack or MinIO usually need "path" (host/bucket/key).
    s3_addressing_style: Literal["virtual", "path"] = "virtual"
    sqs_queue_url: str | None = None
    sqs_wait_seconds: int = 20  # long polling
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def effective_database_url(self) -> str:
        """The URL to connect to: the `DB_*` parts if `DB_HOST` is set, else `DATABASE_URL`."""
        if self.db_host:
            return URL.create(
                "postgresql+psycopg",
                username=self.db_user,
                password=self.db_password.get_secret_value() if self.db_password else None,
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                query={"sslmode": self.db_sslmode},
            ).render_as_string(hide_password=False)
        return normalize_database_url(self.database_url)

    @model_validator(mode="after")
    def _modes_have_what_they_need(self) -> Self:
        if self.environment != "local" and self.effective_database_url.startswith(SQLITE_PREFIX):
            raise ValueError(
                "SQLite is only allowed when ENVIRONMENT=local. Set DB_HOST (with DB_PASSWORD) "
                "or a PostgreSQL DATABASE_URL."
            )
        if self.storage_mode == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_MODE=s3.")
        if self.job_mode == "sqs" and not self.sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL is required when JOB_MODE=sqs.")
        if not 1 <= self.s3_presign_expires_seconds <= 3600:
            raise ValueError("S3_PRESIGN_EXPIRES_SECONDS must be between 1 and 3600.")
        if not 0 <= self.sqs_wait_seconds <= 20:
            raise ValueError("SQS_WAIT_SECONDS must be between 0 and 20.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
