"""Keyed token-bucket rate limiter (one bucket per client), in process memory.

The api runs as ONE gunicorn worker process with N threads precisely so that this limiter sees every
request; with several worker processes each would keep its own buckets and the effective limit would
be multiplied by the process count.
"""

import math
import threading
import time
from collections.abc import Callable

# A full bucket is indistinguishable from a missing one, so dropping an idle bucket is lossless.
IDLE_TTL_S = 600.0
SWEEP_EVERY_S = 60.0


class RateLimiter:
    def __init__(self, per_minute: int, burst: int, clock: Callable[[], float] = time.monotonic):
        self.per_second = per_minute / 60
        self.burst = float(max(burst, 1))
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last refill)
        self._lock = threading.Lock()
        self._last_sweep = clock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Consume a token for key. When denied, also return how many seconds to wait before retrying."""
        with self._lock:
            now = self.clock()
            self._sweep(now)
            tokens, last = self._buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.per_second)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            if self.per_second <= 0:
                return False, 3600.0
            return False, (1 - tokens) / self.per_second

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < SWEEP_EVERY_S:
            return
        self._last_sweep = now
        for key in [k for k, (_, last) in self._buckets.items() if now - last > IDLE_TTL_S]:
            del self._buckets[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)


def retry_after_seconds(wait_s: float) -> int:
    return max(1, math.ceil(wait_s))
