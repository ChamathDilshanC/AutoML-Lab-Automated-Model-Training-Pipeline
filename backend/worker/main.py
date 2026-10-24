"""Training worker entry point: `python -m worker.main`.

A separate process from the API, so training never depends on an open web request. In `db` job mode
it polls the metadata database for `QUEUED` experiments; in `sqs` mode it long-polls the queue
(docs/ADR/0005).
"""

import argparse
import logging
import signal
import threading
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.services.aws import build_queue, build_storage
from worker.jobs import process_message, process_next, run_loop, run_sqs_loop

logger = logging.getLogger("worker")


def _stop_on_signals(stop: threading.Event) -> None:
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())


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

    storage = build_storage(settings)
    poll_seconds = args.poll_seconds or settings.worker_poll_seconds

    if settings.job_mode == "sqs":
        queue = build_queue(settings)
        if args.once:
            message = queue.receive()
            if message is not None:
                process_message(
                    SessionLocal,
                    storage,
                    queue,
                    message,
                    max_artifact_bytes=settings.max_artifact_bytes,
                )
            return 0
        stop = threading.Event()
        _stop_on_signals(stop)
        logger.info("Worker started; long-polling the SQS queue")
        run_sqs_loop(
            SessionLocal,
            storage,
            queue,
            job_timeout_seconds=settings.job_timeout_seconds,
            max_artifact_bytes=settings.max_artifact_bytes,
            should_stop=stop.is_set,
            on_error_sleep=stop.wait,
        )
        logger.info("Worker stopped")
        return 0

    if args.once:
        process_next(
            SessionLocal,
            storage,
            job_timeout_seconds=settings.job_timeout_seconds,
            max_artifact_bytes=settings.max_artifact_bytes,
        )
        return 0

    stop = threading.Event()
    _stop_on_signals(stop)

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
