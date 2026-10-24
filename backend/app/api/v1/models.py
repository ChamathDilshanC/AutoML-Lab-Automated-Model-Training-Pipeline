from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import enforce_predict_rate_limit, get_storage
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.db import registry as repo
from app.db.audit import record_audit
from app.db.models import RegisteredModel
from app.db.session import get_session
from app.schemas.models import (
    ModelApproveRequest,
    ModelResponse,
    ModelRevokeRequest,
    PredictionRequest,
    PredictionResponse,
)
from app.services import models as model_service
from app.services.storage import StorageAdapter

router = APIRouter(prefix="/models", tags=["models"])

SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[StorageAdapter, Depends(get_storage)]
OwnerDep = Annotated[str, Depends(get_owner_id)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _owned_model(session: Session, owner_id: str, model_id: str) -> RegisteredModel:
    model = repo.get_model(session, owner_id, model_id)
    if model is None:  # also returned for other owners' models
        raise ApiError(404, "NOT_FOUND", "Model not found.")
    return model


def _response(session: Session, model: RegisteredModel) -> ModelResponse:
    names = model_service.filenames_for(session, [model])
    return model_service.to_response(model, names.get(model.dataset_id))


@router.get("", response_model=list[ModelResponse])
def list_models(session: SessionDep, owner_id: OwnerDep) -> list[ModelResponse]:
    """Registered models, newest first. Not paginated yet."""
    models = repo.list_models(session, owner_id)
    names = model_service.filenames_for(session, models)
    return [model_service.to_response(m, names.get(m.dataset_id)) for m in models]


@router.get("/{model_id}", response_model=ModelResponse)
def read_model(model_id: str, session: SessionDep, owner_id: OwnerDep) -> ModelResponse:
    return _response(session, _owned_model(session, owner_id, model_id))


@router.post("/{model_id}/approve", response_model=ModelResponse)
def approve_model(
    model_id: str, body: ModelApproveRequest, session: SessionDep, owner_id: OwnerDep
) -> ModelResponse:
    """Approve a model for predictions. Approving an approved model is a no-op."""
    model = model_service.approve(session, _owned_model(session, owner_id, model_id))
    record_audit(
        session, "model.approve", actor_id=owner_id, resource_type="model", resource_id=model_id
    )
    return _response(session, model)


@router.post("/{model_id}/revoke", response_model=ModelResponse)
def revoke_model(
    model_id: str, body: ModelRevokeRequest, session: SessionDep, owner_id: OwnerDep
) -> ModelResponse:
    """Stop an approved model from serving predictions. This cannot be undone."""
    model = model_service.revoke(session, _owned_model(session, owner_id, model_id))
    record_audit(
        session, "model.revoke", actor_id=owner_id, resource_type="model", resource_id=model_id
    )
    return _response(session, model)


@router.post(
    "/{model_id}/predict",
    response_model=PredictionResponse,
    dependencies=[Depends(enforce_predict_rate_limit)],
)
def predict(
    model_id: str,
    payload: PredictionRequest,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    owner_id: OwnerDep,
    settings: SettingsDep,
) -> PredictionResponse:
    """Run an approved model on JSON instances validated against its feature schema."""
    model = _owned_model(session, owner_id, model_id)
    return model_service.predict(
        storage,
        model,
        payload.instances,
        max_batch=settings.max_prediction_batch,
        request_id=getattr(request.state, "request_id", None),
    )
