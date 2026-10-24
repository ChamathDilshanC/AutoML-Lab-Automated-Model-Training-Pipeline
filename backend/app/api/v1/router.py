from fastapi import APIRouter, Depends

from app.api.v1 import auth, datasets, experiments, models
from app.core.security import get_current_user

api_v1_router = APIRouter(prefix="/api/v1")

# Sign-in is the only public route. Everything else requires a valid token, enforced here once so
# a new router cannot be added unprotected by accident (a test walks every route to check).
api_v1_router.include_router(auth.router)
protected = [Depends(get_current_user)]
api_v1_router.include_router(datasets.router, dependencies=protected)
api_v1_router.include_router(experiments.router, dependencies=protected)
api_v1_router.include_router(models.router, dependencies=protected)
