from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.services.storage import LocalStorage, StorageAdapter


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> StorageAdapter:
    return LocalStorage(Path(settings.artifact_dir))


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
