"""Training worker entry point.

Job claiming and execution are implemented in milestone M4. For now this only confirms that the
worker module can be started.
"""

import logging

logger = logging.getLogger("worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Worker started. Job processing is not implemented yet (milestone M4).")


if __name__ == "__main__":
    main()
