import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.headers import SecurityHeadersMiddleware
from app.core.limits import BodyLimitMiddleware
from app.core.rate_limit import RateLimiter
from app.core.request_id import RequestIdMiddleware
from app.core.tokens import resolve_secret_key
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.session import Base, SessionLocal, engine
from app.services.reaper import run_reaper


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Interim: create tables on start-up until a migration tool is chosen
    # (see docs/DATABASE_SCHEMA.md).
    Base.metadata.create_all(engine)
    stop = asyncio.Event()
    reaper = asyncio.create_task(
        run_reaper(
            SessionLocal, settings.job_timeout_seconds, settings.reaper_interval_seconds, stop
        )
    )
    try:
        yield
    finally:
        stop.set()
        await reaper


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    resolve_secret_key(settings)  # fail at start-up, not on the first sign-in, if misconfigured

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.predict_limiter = RateLimiter(settings.predict_rate_limit_per_minute)
    app.state.login_limiter = RateLimiter(settings.login_rate_limit_per_minute)
    register_exception_handlers(app)

    # Middleware added last is outermost: security headers wrap the request ID, which wraps CORS,
    # which wraps the body limit.
    app.add_middleware(BodyLimitMiddleware, max_body_bytes=settings.max_upload_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()
