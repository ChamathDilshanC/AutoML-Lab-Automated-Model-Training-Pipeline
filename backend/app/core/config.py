from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
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

    @model_validator(mode="after")
    def _modes_have_what_they_need(self) -> Self:
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
