from pathlib import Path
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.storage import LocalStorage, StorageAdapter


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> StorageAdapter:
    return LocalStorage(Path(settings.artifact_dir))
