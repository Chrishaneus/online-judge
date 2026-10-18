"""Token-bucket limiter (ported from rest's ratelimit_test.go)."""

from app.controllers.rate_limit import IDLE_TTL_S, RateLimiter, retry_after_seconds


class FakeClock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def limiter(per_min, burst):
    clock = FakeClock()
    return RateLimiter(per_min, burst, clock=clock), clock


def test_burst_then_deny():
    lim, _ = limiter(60, 3)
    for _ in range(3):
        assert lim.allow("a")[0]
    ok, wait = lim.allow("a")
    assert not ok
    assert 0 < wait <= 1


def test_refill():
    lim, clock = limiter(60, 1)  # 1 token / second
    lim.allow("a")
    assert not lim.allow("a")[0]
    clock.advance(1.1)
    assert lim.allow("a")[0]


def test_keys_are_independent():
    lim, _ = limiter(60, 1)
    lim.allow("a")
    assert lim.allow("b")[0]


def test_sweep_drops_idle_buckets():
    lim, clock = limiter(60, 1)
    lim.allow("a")
    lim.allow("b")
    clock.advance(IDLE_TTL_S + 60)
    lim.allow("c")
    assert len(lim) == 1


def test_zero_rate_and_burst_floor():
    lim, _ = limiter(0, 0)  # burst is at least 1
    assert lim.allow("a")[0]
    ok, wait = lim.allow("a")
    assert not ok and wait == 3600


def test_retry_after_is_whole_seconds_at_least_one():
    assert retry_after_seconds(0.01) == 1
    assert retry_after_seconds(1.0) == 1
    assert retry_after_seconds(1.2) == 2
