from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.services.job_queue import JobPublisher
from app.services.storage import StorageAdapter


def get_storage(request: Request) -> StorageAdapter:
    """The storage adapter built at start-up from `STORAGE_MODE`."""
    storage: StorageAdapter = request.app.state.storage
    return storage


def get_publisher(request: Request) -> JobPublisher:
    """Hands queued experiments to the workers, per `JOB_MODE`."""
    publisher: JobPublisher = request.app.state.publisher
    return publisher


def enforce_predict_rate_limit(
    request: Request, owner_id: Annotated[str, Depends(get_owner_id)]
) -> None:
    """Limit predictions per signed-in user (all models together), before any work is done."""
    allowed, retry_after = request.app.state.predict_limiter.check(f"predict:{owner_id}")
    if not allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many prediction requests. Slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
