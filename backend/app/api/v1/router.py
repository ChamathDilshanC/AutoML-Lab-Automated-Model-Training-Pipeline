from fastapi import APIRouter

from app.api.v1 import datasets, experiments

# Further versioned routes (models) are added here in later milestones.
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(datasets.router)
api_v1_router.include_router(experiments.router)
