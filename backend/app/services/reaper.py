"""Background reaper for abandoned experiments.

The worker also reaps on every poll, but a crashed worker that is not restarted would leave
experiments `RUNNING` forever. Running the same check inside the API process covers that case.
The update is conditional, so the API and the worker reaping at the same time is harmless.
"""

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from app.db.experiments import reap_stale

logger = logging.getLogger(__name__)


async def run_reaper(
    session_factory: sessionmaker[Session],
    timeout_seconds: int,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    """Fail stale `RUNNING` experiments every `interval_seconds` until `stop` is set."""
    while not stop.is_set():
        try:
            reaped = await asyncio.to_thread(reap_stale, session_factory, timeout_seconds)
            if reaped:
                logger.warning("Marked %d stale experiment(s) as FAILED", reaped)
        except Exception:
            logger.exception("Reaper pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
