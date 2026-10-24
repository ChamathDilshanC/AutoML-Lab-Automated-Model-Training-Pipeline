"""Building the storage adapter and job publisher that settings ask for.

Credentials are never configured here: boto3 finds them through the standard chain (environment
variables, shared config or SSO profile, instance or task role).
"""

from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import Settings
from app.services.job_queue import JobPublisher, NullPublisher, SqsQueue
from app.services.storage import LocalStorage, S3Storage, StorageAdapter


def _config(settings: Settings) -> Config:
    return Config(
        signature_version="s3v4",
        # Regional virtual-hosted URLs (bucket.s3.<region>.amazonaws.com) for AWS. The global
        # endpoint answers a PUT to a bucket in another region with a redirect a browser cannot
        # follow.
        s3={"addressing_style": settings.s3_addressing_style},
        retries={"max_attempts": 3, "mode": "standard"},
    )


def make_s3_client(settings: Settings) -> Any:
    return boto3.client("s3", region_name=settings.aws_region, config=_config(settings))


def make_sqs_client(settings: Settings) -> Any:
    return boto3.client("sqs", region_name=settings.aws_region, config=_config(settings))


def build_storage(settings: Settings) -> StorageAdapter:
    if settings.storage_mode == "s3":
        assert settings.s3_bucket  # checked by Settings
        return S3Storage(
            make_s3_client(settings), settings.s3_bucket, settings.s3_presign_expires_seconds
        )
    return LocalStorage(Path(settings.artifact_dir))


def build_queue(settings: Settings) -> SqsQueue:
    assert settings.sqs_queue_url  # checked by Settings
    return SqsQueue(make_sqs_client(settings), settings.sqs_queue_url, settings.sqs_wait_seconds)


def build_publisher(settings: Settings) -> JobPublisher:
    """In `db` mode workers find queued rows themselves, so there is nothing to publish."""
    return build_queue(settings) if settings.job_mode == "sqs" else NullPublisher()
