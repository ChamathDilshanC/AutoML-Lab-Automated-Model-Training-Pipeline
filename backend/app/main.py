import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.limits import BodyLimitMiddleware
from app.core.request_id import RequestIdMiddleware
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Interim: create tables on start-up until a migration tool is chosen
    # (see docs/DATABASE_SCHEMA.md).
    Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_exception_handlers(app)

    # Middleware added last is outermost: request ID wraps CORS, which wraps the body limit.
    app.add_middleware(BodyLimitMiddleware, max_body_bytes=settings.max_upload_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()
