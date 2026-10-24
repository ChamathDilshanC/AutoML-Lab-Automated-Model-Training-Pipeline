"""Training worker entry point: `python -m worker.main`.

A separate process from the API. It polls the metadata database for `QUEUED` experiments and runs
them, so training never depends on an open web request.
"""

import argparse
import logging
import signal
import threading
from collections.abc import Sequence
from pathlib import Path

from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.services.storage import LocalStorage
from worker.jobs import process_next, run_loop

logger = logging.getLogger("worker")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AutoML Lab training worker")
    parser.add_argument("--once", action="store_true", help="process at most one job, then exit")
    parser.add_argument("--poll-seconds", type=float, help="seconds to wait when idle")
    args = parser.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    # Safe to repeat: lets the worker start before the API has created the tables.
    Base.metadata.create_all(engine)

    storage = LocalStorage(Path(settings.artifact_dir))
    poll_seconds = args.poll_seconds or settings.worker_poll_seconds

    if args.once:
        process_next(
            SessionLocal,
            storage,
            job_timeout_seconds=settings.job_timeout_seconds,
            max_artifact_bytes=settings.max_artifact_bytes,
        )
        return 0

    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())

    logger.info("Worker started; polling every %.1fs", poll_seconds)
    run_loop(
        SessionLocal,
        storage,
        poll_seconds=poll_seconds,
        job_timeout_seconds=settings.job_timeout_seconds,
        max_artifact_bytes=settings.max_artifact_bytes,
        should_stop=stop.is_set,
        sleep=stop.wait,
    )
    logger.info("Worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
