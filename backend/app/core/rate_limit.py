"""In-memory token-bucket rate limiter.

State lives in one process. With several API processes or instances each keeps its own buckets, so
the effective limit is multiplied; a shared store (for example Redis) or a gateway limit is needed
for that, which is part of the cloud milestone.
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """Allows `limit` requests per `window_seconds` per key, with bursts up to `limit`."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self.rate = limit / window_seconds  # tokens added per second
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Take one token. Returns (allowed, seconds to wait before retrying)."""
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._prune(now)
                bucket = self._buckets[key] = _Bucket(tokens=float(self.limit), updated=now)
            else:
                elapsed = max(0.0, now - bucket.updated)
                bucket.tokens = min(float(self.limit), bucket.tokens + elapsed * self.rate)
                bucket.updated = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0
            wait = (1.0 - bucket.tokens) / self.rate
            return False, max(1, math.ceil(wait))

    def _prune(self, now: float) -> None:
        """Drop buckets that have refilled completely; they behave like new ones."""
        full_after = self.window
        stale = [k for k, b in self._buckets.items() if now - b.updated >= full_after]
        for key in stale:
            del self._buckets[key]
        if len(self._buckets) >= self._max_keys:  # still full of active keys: drop the oldest
            oldest = sorted(self._buckets, key=lambda k: self._buckets[k].updated)
            for key in oldest[: len(oldest) // 10 + 1]:
                del self._buckets[key]
